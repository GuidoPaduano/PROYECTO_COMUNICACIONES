from __future__ import annotations

from typing import Optional

from django.core.cache import cache
from django.db.models import Avg, Case, CharField, Count, F, Q, Value, When
from django.db.models.functions import TruncMonth, Trim, Upper

from ..course_access import (
    build_course_membership_q,
    filter_course_options_by_refs,
    get_assignment_course_refs,
)
from ..models import Alumno, Nota, resolve_school_course_for_value
from ..schools import get_request_school, scope_queryset_to_school
from ..user_groups import get_user_group_names, user_in_groups
from ..utils_cursos import get_course_label, get_school_course_by_id, get_school_course_choices, resolve_course_reference

try:
    from ..models_preceptores import PreceptorCurso, ProfesorCurso  # type: ignore
except Exception:
    PreceptorCurso = None
    ProfesorCurso = None

ESTADOS = ("TEA", "TEP", "TED")


def _active_school_id(school) -> str:
    sid = getattr(school, "id", None)
    return str(sid) if sid is not None else "none"


def _available_course_codes(school=None) -> list[str]:
    return [str(code) for code, _name in get_school_course_choices(school=school)]


def _course_codes_for_refs(refs, *, school=None) -> list[str]:
    options = [
        {"code": str(code), "id": str(code)}
        for code, _name in get_school_course_choices(school=school)
    ]
    return [
        str(option.get("code") or "")
        for option in filter_course_options_by_refs(options, refs)
        if str(option.get("code") or "")
    ]


def _round2(value) -> float:
    try:
        return round(float(value), 2)
    except Exception:
        return 0.0


def _safe_pct(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return _round2((part * 100.0) / total)


def _user_groups(user) -> set[str]:
    return set(get_user_group_names(user))


def _role_label(user) -> str:
    if getattr(user, "is_superuser", False):
        return "Superuser"
    if user_in_groups(user, "Padres"):
        return "Padres"
    if user_in_groups(user, "Alumnos", "Alumno"):
        return "Alumnos"
    if user_in_groups(user, "Profesores"):
        return "Profesores"
    if user_in_groups(user, "Directivos", "Directivo"):
        return "Directivos"
    if user_in_groups(user, "Preceptores", "Preceptor"):
        return "Preceptores"
    return "SinRol"


def _mis_estadisticas_cache_key(*, user_id, role, school_id, alumno_param, anio, cuatrimestre, materia) -> str:
    return (
        f"reportes:v2:mis_estadisticas:u{user_id}:r{role}:s{school_id or 'none'}:"
        f"a{alumno_param or 'default'}:y{anio or 'all'}:q{cuatrimestre or 'all'}:m{materia or 'all'}"
    )


def _serialize_alumno(a: Alumno) -> dict:
    school_course = getattr(a, "school_course", None)
    return {
        "id": a.id,
        "id_alumno": getattr(a, "id_alumno", None),
        "nombre": getattr(a, "nombre", ""),
        "school_course_id": getattr(a, "school_course_id", None),
        "school_course_name": getattr(school_course, "name", None)
        or getattr(school_course, "code", None)
        or getattr(a, "curso", ""),
    }


def _serialize_nota_detalle(nota: Nota) -> dict:
    promedio = getattr(nota, "nota_numerica", None)
    return {
        "id": nota.id,
        "fecha": nota.fecha.isoformat() if getattr(nota, "fecha", None) else None,
        "materia": getattr(nota, "materia", None),
        "tipo": getattr(nota, "tipo", None),
        "calificacion": getattr(nota, "calificacion", None),
        "resultado": getattr(nota, "resultado", None),
        "nota_numerica": float(promedio) if promedio is not None else None,
        "cuatrimestre": getattr(nota, "cuatrimestre", None),
        "observaciones": getattr(nota, "observaciones", None),
    }


def _course_payload(*, school=None, course_code="", school_course=None) -> dict:
    resolved_school_course = school_course
    resolved_code = _normalize_curso(
        getattr(resolved_school_course, "code", None) or course_code,
        school=school,
    )
    course_name = (
        getattr(resolved_school_course, "name", None)
        or getattr(resolved_school_course, "code", None)
        or get_course_label(resolved_code, school=school)
        or resolved_code
        or None
    )
    return {
        "curso": resolved_code,
        "school_course_id": getattr(resolved_school_course, "id", None),
        "school_course_name": course_name,
    }


def _public_course_payload(*, school=None, course_code="", school_course=None) -> dict:
    return {
        key: value
        for key, value in _course_payload(
            school=school,
            course_code=course_code,
            school_course=school_course,
        ).items()
        if key != "curso"
    }


def _normalize_curso(curso: str, school=None) -> str:
    raw = (curso or "").strip()
    if not raw:
        return ""

    try:
        mapping = {str(k).upper(): str(k) for k, _ in get_school_course_choices(school=school)}
    except Exception:
        mapping = {}

    return mapping.get(raw.upper(), raw)


def _resolve_path_course_selection(
    raw_value,
    *,
    school=None,
):
    raw = (raw_value or "").strip()
    if not raw:
        return None, "", "Falta el campo requerido: school_course_id o curso."

    school_course = get_school_course_by_id(raw, school=school, include_inactive=True)
    if school_course is not None:
        return school_course, _normalize_curso(getattr(school_course, "code", ""), school=school), None

    school_course, course_code, error = resolve_course_reference(
        school=school,
        raw_course=raw,
        required=True,
        include_inactive=True,
        deprecated_course_error="El código legacy de curso en la ruta está deprecado. Usa school_course_id.",
    )
    return school_course, _normalize_curso(course_code, school=school), error


def _filter_notas_por_curso(qs, curso: str, *, school=None, school_course=None):
    curso_norm = _normalize_curso(curso, school=school)
    if not curso_norm:
        return qs.none()

    resolved_school_course = school_course
    if resolved_school_course is None and school is not None:
        resolved_school_course = resolve_school_course_for_value(school=school, curso=curso_norm)
    course_q = build_course_membership_q(
        school_course_id=getattr(resolved_school_course, "id", None),
        course_code=curso_norm,
        school_course_field="alumno__school_course",
        code_field="alumno__curso",
    )
    if course_q is None:
        return qs.none()
    return qs.filter(course_q)


def _normalize_cuatrimestre(raw: str) -> Optional[int]:
    txt = (raw or "").strip()
    if not txt:
        return None
    try:
        val = int(txt)
    except Exception:
        return None
    if val not in (1, 2):
        return None
    return val


def _normalize_anio(raw: str) -> Optional[int]:
    txt = str(raw or "").strip()
    if not txt or txt.lower() in {"all", "todos", "todas"}:
        return None
    try:
        val = int(txt)
    except Exception:
        return None
    if val < 2000 or val > 2100:
        return None
    return val


def _resolve_profesor_cursos(user, school=None) -> list[str]:
    if getattr(user, "is_superuser", False):
        return sorted(set(_available_course_codes(school)))

    cache_key = f"reportes:v2:cursos_profesor:u{getattr(user, 'id', 'x')}:s{_active_school_id(school)}"
    cached = cache.get(cache_key)
    if cached is not None:
        return list(cached)

    if ProfesorCurso is not None:
        try:
            refs = _resolve_profesor_course_refs(user, school=school)
            out = _course_codes_for_refs(refs, school=school)
            cache.set(cache_key, out, 180)
            return out
        except Exception:
            cache.set(cache_key, [], 60)
            return []

    valid = set(_available_course_codes(school))
    from_groups = sorted(valid.intersection(_user_groups(user)))
    if from_groups:
        cache.set(cache_key, from_groups, 180)
        return from_groups

    out = sorted(valid)
    cache.set(cache_key, out, 180)
    return out


def _resolve_preceptor_cursos(user, school=None) -> list[str]:
    if getattr(user, "is_superuser", False):
        return sorted(set(_available_course_codes(school)))

    cache_key = f"reportes:v2:cursos_preceptor:u{getattr(user, 'id', 'x')}:s{_active_school_id(school)}"
    cached = cache.get(cache_key)
    if cached is not None:
        return list(cached)

    if PreceptorCurso is not None:
        try:
            refs = _resolve_preceptor_course_refs(user, school=school)
            out = _course_codes_for_refs(refs, school=school)
            cache.set(cache_key, out, 180)
            return out
        except Exception:
            cache.set(cache_key, [], 60)
            return []

    valid = set(_available_course_codes(school))
    from_groups = sorted(valid.intersection(_user_groups(user)))
    cache.set(cache_key, from_groups, 180)
    return from_groups


def _resolve_profesor_course_refs(user, school=None):
    if getattr(user, "is_superuser", False) or ProfesorCurso is None:
        return []
    school_id = getattr(school, "id", None) or 0
    cached = getattr(user, "_cached_reportes_profesor_refs_by_school", None)
    if isinstance(cached, dict) and school_id in cached:
        return list(cached[school_id])
    try:
        qs = scope_queryset_to_school(ProfesorCurso.objects.filter(profesor=user), school)
        refs = get_assignment_course_refs(qs)
        try:
            if not isinstance(cached, dict):
                cached = {}
            cached[school_id] = tuple(refs)
            setattr(user, "_cached_reportes_profesor_refs_by_school", cached)
        except Exception:
            pass
        return refs
    except Exception:
        return []


def _resolve_preceptor_course_refs(user, school=None):
    if getattr(user, "is_superuser", False) or PreceptorCurso is None:
        return []
    school_id = getattr(school, "id", None) or 0
    cached = getattr(user, "_cached_reportes_preceptor_refs_by_school", None)
    if isinstance(cached, dict) and school_id in cached:
        return list(cached[school_id])
    try:
        qs = scope_queryset_to_school(PreceptorCurso.objects.filter(preceptor=user), school)
        refs = get_assignment_course_refs(qs)
        try:
            if not isinstance(cached, dict):
                cached = {}
            cached[school_id] = tuple(refs)
            setattr(user, "_cached_reportes_preceptor_refs_by_school", cached)
        except Exception:
            pass
        return refs
    except Exception:
        return []


def _resolve_materia(raw: str) -> Optional[str]:
    txt = (raw or "").strip()
    if not txt:
        return None

    choices = list(getattr(Nota, "MATERIAS", []))
    if txt.isdigit():
        idx = int(txt) - 1
        if 0 <= idx < len(choices):
            return str(choices[idx][0])

    txt_low = txt.lower()
    for key, label in choices:
        if str(key).lower() == txt_low or str(label).lower() == txt_low:
            return str(key)

    return None


def _normalize_materia_filter(raw: str) -> Optional[str]:
    txt = str(raw or "").strip()
    if not txt or txt.lower() in {"all", "todas", "todos"}:
        return None
    return _resolve_materia(txt) or txt


def _annotate_estado_notas(qs):
    return (
        qs.annotate(calificacion_normalizada=Upper(Trim("calificacion")))
        .annotate(
            estado_reporte=Case(
                When(resultado__in=ESTADOS, then=F("resultado")),
                When(calificacion_normalizada="TEA", then=Value("TEA")),
                When(calificacion_normalizada="TEP", then=Value("TEP")),
                When(calificacion_normalizada="TED", then=Value("TED")),
                default=Value(None),
                output_field=CharField(),
            )
        )
    )


def _build_notas_payload(base_qs):
    qs = _annotate_estado_notas(base_qs)

    summary = qs.aggregate(
        total_evaluaciones=Count("id"),
        TEA=Count("id", filter=Q(estado_reporte="TEA")),
        TEP=Count("id", filter=Q(estado_reporte="TEP")),
        TED=Count("id", filter=Q(estado_reporte="TED")),
    )

    total = int(summary.get("total_evaluaciones") or 0)
    tea = int(summary.get("TEA") or 0)
    tep = int(summary.get("TEP") or 0)
    ted = int(summary.get("TED") or 0)

    resumen_notas = {
        "total_evaluaciones": total,
        "conteos_por_estado": {"TEA": tea, "TEP": tep, "TED": ted},
        "porcentajes_por_estado": {
            "TEA": _safe_pct(tea, total),
            "TEP": _safe_pct(tep, total),
            "TED": _safe_pct(ted, total),
        },
    }

    por_materia_rows = (
        qs.values("materia")
        .annotate(
            total=Count("id"),
            TEA_count=Count("id", filter=Q(estado_reporte="TEA")),
            TEP_count=Count("id", filter=Q(estado_reporte="TEP")),
            TED_count=Count("id", filter=Q(estado_reporte="TED")),
        )
        .order_by("materia")
    )

    por_materia = []
    for row in por_materia_rows:
        materia_total = int(row.get("total") or 0)
        tea_count = int(row.get("TEA_count") or 0)
        tep_count = int(row.get("TEP_count") or 0)
        ted_count = int(row.get("TED_count") or 0)
        por_materia.append(
            {
                "materia_id": row.get("materia"),
                "materia_nombre": row.get("materia"),
                "total": materia_total,
                "TEA_count": tea_count,
                "TEP_count": tep_count,
                "TED_count": ted_count,
                "TEA_pct": _safe_pct(tea_count, materia_total),
            }
        )

    evolucion_rows = (
        qs.annotate(mes=TruncMonth("fecha"))
        .values("mes")
        .annotate(
            total=Count("id"),
            evaluaciones_numericas=Count("nota_numerica"),
            promedio_numerico=Avg("nota_numerica"),
            TEA_count=Count("id", filter=Q(estado_reporte="TEA")),
            TEP_count=Count("id", filter=Q(estado_reporte="TEP")),
            TED_count=Count("id", filter=Q(estado_reporte="TED")),
        )
        .order_by("mes")
    )

    evolucion_mensual_notas = []
    for row in evolucion_rows:
        mes = row.get("mes")
        if not mes:
            continue
        total_mes = int(row.get("total") or 0)
        tea_mes = int(row.get("TEA_count") or 0)
        evolucion_mensual_notas.append(
            {
                "mes": mes.strftime("%Y-%m"),
                "total": total_mes,
                "evaluaciones_numericas": int(row.get("evaluaciones_numericas") or 0),
                "promedio_numerico": _round2(row.get("promedio_numerico")) if row.get("promedio_numerico") is not None else None,
                "TEA_count": tea_mes,
                "TEP_count": int(row.get("TEP_count") or 0),
                "TED_count": int(row.get("TED_count") or 0),
                "TEA_pct": _safe_pct(tea_mes, total_mes),
            }
        )

    if por_materia:
        materia_mas_floja = min(
            por_materia,
            key=lambda x: (x["TEA_pct"], -x["TED_count"]),
        )
        materia_mas_floja = {
            "materia_id": materia_mas_floja["materia_id"],
            "materia_nombre": materia_mas_floja["materia_nombre"],
            "TEA_pct": materia_mas_floja["TEA_pct"],
            "TED_count": materia_mas_floja["TED_count"],
        }
    else:
        materia_mas_floja = None

    return {
        "resumen_notas": resumen_notas,
        "por_materia": por_materia,
        "evolucion_mensual_notas": evolucion_mensual_notas,
        "materia_mas_floja": materia_mas_floja,
    }


def _build_historial_anual_payload(base_qs):
    qs = _annotate_estado_notas(base_qs)
    rows = (
        qs.values("fecha__year")
        .annotate(
            total=Count("id"),
            evaluaciones_numericas=Count("nota_numerica"),
            promedio_numerico=Avg("nota_numerica"),
            TEA_count=Count("id", filter=Q(estado_reporte="TEA")),
            TEP_count=Count("id", filter=Q(estado_reporte="TEP")),
            TED_count=Count("id", filter=Q(estado_reporte="TED")),
        )
        .order_by("fecha__year")
    )

    historial = []
    for row in rows:
        anio = row.get("fecha__year")
        if anio is None:
            continue
        total = int(row.get("total") or 0)
        tea = int(row.get("TEA_count") or 0)
        tep = int(row.get("TEP_count") or 0)
        ted = int(row.get("TED_count") or 0)
        historial.append(
            {
                "anio": int(anio),
                "total": total,
                "evaluaciones_numericas": int(row.get("evaluaciones_numericas") or 0),
                "promedio_numerico": _round2(row.get("promedio_numerico")) if row.get("promedio_numerico") is not None else None,
                "TEA_count": tea,
                "TEP_count": tep,
                "TED_count": ted,
                "TEA_pct": _safe_pct(tea, total),
                "TEP_pct": _safe_pct(tep, total),
                "TED_pct": _safe_pct(ted, total),
            }
        )
    return historial


def _apply_cuatrimestre_filter(notas_qs, cuatrimestre: Optional[int]):
    if cuatrimestre in (1, 2):
        return notas_qs.filter(cuatrimestre=cuatrimestre)
    return notas_qs


def _apply_anio_filter(notas_qs, anio: Optional[int]):
    if anio is not None:
        return notas_qs.filter(fecha__year=anio)
    return notas_qs


def _apply_materia_filter(notas_qs, materia: Optional[str]):
    if materia:
        return notas_qs.filter(materia=materia)
    return notas_qs


def _resolve_reporte_alumno_en_curso(*, raw_alumno, curso: str, school=None, school_course=None):
    alumno_param = str(raw_alumno or "").strip()
    if not alumno_param:
        return None, "Falta el parámetro alumno_id."

    alumnos_qs = scope_queryset_to_school(
        Alumno.objects.select_related("school_course"),
        school,
    )
    if alumno_param.isdigit():
        alumno = alumnos_qs.filter(id=int(alumno_param)).first()
    else:
        alumno = alumnos_qs.filter(id_alumno__iexact=alumno_param).first()

    if not alumno:
        return None, "Alumno no encontrado."

    course_q = build_course_membership_q(
        school_course_id=getattr(school_course, "id", None),
        course_code=curso,
        school_course_field="school_course",
        code_field="curso",
    )
    if course_q is None or not Alumno.objects.filter(id=alumno.id).filter(course_q).exists():
        return None, "El alumno no pertenece al curso seleccionado."

    return alumno, None


def _build_alumno_historico_payload(
    *,
    alumno: Alumno,
    notas_qs,
    notas_qs_historicas,
    role: str,
    school=None,
    curso="",
    school_course=None,
    cuatrimestre=None,
    anio=None,
    materia=None,
):
    notas_payload = _build_notas_payload(notas_qs)
    historial_anual = _build_historial_anual_payload(notas_qs_historicas)
    detalle_rows = list(notas_qs.order_by("-fecha", "-id"))
    historial_detallado = [_serialize_nota_detalle(nota) for nota in detalle_rows]
    notas_numericas = [
        float(nota.nota_numerica)
        for nota in detalle_rows
        if getattr(nota, "nota_numerica", None) is not None
    ]
    promedio_numerico = (sum(notas_numericas) / len(notas_numericas)) if notas_numericas else None
    ultima_nota = detalle_rows[0] if detalle_rows else None

    return {
        "scope": "alumno_historico",
        "rol": role,
        **_public_course_payload(school=school, course_code=curso, school_course=school_course),
        "alumno_activo": _serialize_alumno(alumno),
        "filtros": {"cuatrimestre": cuatrimestre, "anio": anio, "materia": materia},
        "anios_disponibles": [row["anio"] for row in historial_anual],
        "historial_anual": historial_anual,
        "promedio_general_numerico": _round2(promedio_numerico) if promedio_numerico is not None else None,
        "evaluaciones_numericas": len(notas_numericas),
        "ultima_evaluacion": _serialize_nota_detalle(ultima_nota) if ultima_nota else None,
        "historial_detallado": historial_detallado,
        **notas_payload,
    }
