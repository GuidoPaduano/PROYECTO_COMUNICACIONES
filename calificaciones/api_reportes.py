from __future__ import annotations

from typing import Optional

from django.core.cache import cache
from django.db.models import Case, CharField, Count, F, Q, Value, When
from django.db.models.functions import TruncMonth, Trim, Upper

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .jwt_auth import CookieJWTAuthentication as JWTAuthentication

from .contexto import resolve_alumno_for_user
from .course_access import (
    build_course_membership_q,
    course_ref_matches,
    filter_course_options_by_refs,
    get_assignment_course_refs,
)
from .models import Alumno, Nota, resolve_school_course_for_value
from .schools import get_request_school, scope_queryset_to_school
from .user_groups import get_user_group_names, user_in_groups
from .utils_cursos import get_course_label, get_school_course_by_id, get_school_course_choices, resolve_course_reference

try:
    from .models_preceptores import PreceptorCurso, ProfesorCurso  # type: ignore
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


def _mis_estadisticas_cache_key(*, user_id, role, school_id, alumno_param, cuatrimestre) -> str:
    return (
        f"reportes:v2:mis_estadisticas:u{user_id}:r{role}:s{school_id or 'none'}:"
        f"a{alumno_param or 'default'}:q{cuatrimestre or 'all'}"
    )


def _serialize_alumno(a: Alumno) -> dict:
    return {
        "id": a.id,
        "id_alumno": getattr(a, "id_alumno", None),
        "nombre": getattr(a, "nombre", ""),
        "school_course_id": getattr(a, "school_course_id", None),
        "school_course_name": getattr(getattr(a, "school_course", None), "name", None)
        or getattr(getattr(a, "school_course", None), "code", None)
        or getattr(a, "curso", ""),
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


def _apply_cuatrimestre_filter(notas_qs, cuatrimestre: Optional[int]):
    if cuatrimestre in (1, 2):
        return notas_qs.filter(cuatrimestre=cuatrimestre)
    return notas_qs


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def reportes_mis_estadisticas(request):
    user = request.user
    role = _role_label(user)
    cuatrimestre = _normalize_cuatrimestre(request.GET.get("cuatrimestre"))
    active_school = get_request_school(request)
    alumno_param = (request.GET.get("alumno_id") or "").strip()

    if role not in ("Padres", "Alumnos", "Superuser"):
        return Response({"detail": "No autorizado para este reporte."}, status=403)

    cache_key = _mis_estadisticas_cache_key(
        user_id=getattr(user, "id", None),
        role=role,
        school_id=getattr(active_school, "id", None),
        alumno_param=alumno_param,
        cuatrimestre=cuatrimestre,
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return Response(cached)

    alumnos = []
    selected = None

    if role == "Superuser":
        if not alumno_param:
            return Response({"detail": "Para superusuario envia ?alumno_id=<id o legajo>."}, status=400)
        alumnos_qs = scope_queryset_to_school(
            Alumno.objects.select_related("school_course"),
            active_school,
        )
        if alumno_param.isdigit():
            selected = alumnos_qs.filter(id=int(alumno_param)).first()
        else:
            selected = alumnos_qs.filter(id_alumno__iexact=alumno_param).first()
        if not selected:
            return Response({"detail": "Alumno no encontrado."}, status=404)
        alumnos = [selected]

    elif role == "Padres":
        alumnos_qs = (
            scope_queryset_to_school(
                Alumno.objects.select_related("school_course"),
                active_school,
            )
            .filter(padre=user)
            .order_by("curso", "nombre")
        )
        alumnos = list(alumnos_qs)
        if not alumnos:
            payload = {
                "scope": "mis_estadisticas",
                "rol": role,
                "alumnos": [],
                "alumno_activo": None,
                "resumen_notas": {
                    "total_evaluaciones": 0,
                    "conteos_por_estado": {"TEA": 0, "TEP": 0, "TED": 0},
                    "porcentajes_por_estado": {"TEA": 0.0, "TEP": 0.0, "TED": 0.0},
                },
                "por_materia": [],
                "evolucion_mensual_notas": [],
                "materia_mas_floja": None,
            }
            cache.set(cache_key, payload, 120)
            return Response(payload)

        if not alumno_param:
            selected = alumnos[0]
        elif alumno_param.isdigit():
            selected = alumnos_qs.filter(id=int(alumno_param)).first()
        else:
            selected = alumnos_qs.filter(id_alumno__iexact=alumno_param).first()

        if not selected:
            return Response({"detail": "No autorizado para ese alumno."}, status=403)

    else:  # Alumnos
        resolution = resolve_alumno_for_user(user, school=active_school)
        selected = resolution.alumno
        if not selected:
            return Response({"detail": "No se pudo resolver el alumno asociado al usuario."}, status=404)
        alumnos = [selected]

    notas_qs = scope_queryset_to_school(Nota.objects.filter(alumno=selected), active_school)
    notas_qs = _apply_cuatrimestre_filter(notas_qs, cuatrimestre)

    notas_payload = _build_notas_payload(notas_qs)

    payload = {
        "scope": "mis_estadisticas",
        "rol": role,
        "alumnos": [_serialize_alumno(a) for a in alumnos],
        "alumno_activo": _serialize_alumno(selected),
        "filtros": {"cuatrimestre": cuatrimestre},
        **notas_payload,
    }
    cache.set(cache_key, payload, 120)
    return Response(payload)


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def reportes_por_curso(request, curso: str):
    user = request.user
    role = _role_label(user)
    active_school = get_request_school(request)
    school_course, curso_norm, course_error = _resolve_path_course_selection(
        curso,
        school=active_school,
    )
    cuatrimestre = _normalize_cuatrimestre(request.GET.get("cuatrimestre"))

    if course_error:
        return Response({"detail": course_error}, status=400)

    if role not in ("Profesores", "Preceptores", "Directivos", "Superuser"):
        return Response({"detail": "No autorizado para este reporte."}, status=403)

    if role == "Profesores":
        cursos_habilitados = _resolve_profesor_cursos(user, school=active_school)
        course_refs = _resolve_profesor_course_refs(user, school=active_school)
    elif role == "Directivos":
        cursos_habilitados = sorted(set(_available_course_codes(active_school)))
        course_refs = []
    elif role == "Preceptores":
        cursos_habilitados = _resolve_preceptor_cursos(user, school=active_school)
        course_refs = _resolve_preceptor_course_refs(user, school=active_school)
    else:
        cursos_habilitados = sorted(set(_available_course_codes(active_school)))
        course_refs = []

    # Permiso estricto: si no hay cursos asignados, se deniega.
    if not cursos_habilitados:
        return Response({"detail": "No tenes cursos asignados."}, status=403)

    if course_refs and not course_ref_matches(
        course_refs,
        school_course_id=getattr(school_course, "id", None),
        course_code=curso_norm,
    ):
        return Response({"detail": "No autorizado para ese curso."}, status=403)

    cache_key = f"reportes:v2:curso:u{user.id}:r{role}:s{_active_school_id(active_school)}:c{curso_norm}:q{cuatrimestre or 'all'}"
    cached = cache.get(cache_key)
    if cached is not None:
        return Response(cached)

    notas_qs = _filter_notas_por_curso(
        scope_queryset_to_school(Nota.objects.all(), active_school),
        curso_norm,
        school=active_school,
        school_course=school_course,
    )
    notas_qs = _apply_cuatrimestre_filter(notas_qs, cuatrimestre)

    notas_payload = _build_notas_payload(notas_qs)

    payload = {
        "scope": "curso",
        "rol": role,
        **_public_course_payload(school=active_school, course_code=curso_norm, school_course=school_course),
        "filtros": {"cuatrimestre": cuatrimestre},
        "permisos": {"cursos_habilitados": cursos_habilitados},
        **notas_payload,
    }

    cache.set(cache_key, payload, 120)
    return Response(payload)


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def reportes_materia_curso(request, id_materia: str, curso: str):
    user = request.user
    role = _role_label(user)
    active_school = get_request_school(request)
    school_course, curso_norm, course_error = _resolve_path_course_selection(
        curso,
        school=active_school,
    )
    cuatrimestre = _normalize_cuatrimestre(request.GET.get("cuatrimestre"))

    if course_error:
        return Response({"detail": course_error}, status=400)

    if role not in ("Profesores", "Superuser"):
        return Response({"detail": "Solo profesores pueden acceder a este reporte."}, status=403)

    materia = _resolve_materia(id_materia)
    if not materia:
        return Response({"detail": "Materia invalida."}, status=404)

    if role != "Superuser":
        cursos_habilitados = _resolve_profesor_cursos(user, school=active_school)
        course_refs = _resolve_profesor_course_refs(user, school=active_school)
        if not cursos_habilitados:
            return Response({"detail": "No tenes cursos asignados."}, status=403)
        if course_refs and not course_ref_matches(
            course_refs,
            school_course_id=getattr(school_course, "id", None),
            course_code=curso_norm,
        ):
            return Response({"detail": "No autorizado para ese curso."}, status=403)
    else:
        cursos_habilitados = sorted(set(_available_course_codes(active_school)))

    cache_key = (
        f"reportes:v2:materia_curso:u{user.id}:r{role}:s{_active_school_id(active_school)}:c{curso_norm}:m{materia}:q{cuatrimestre or 'all'}"
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return Response(cached)

    notas_qs = _filter_notas_por_curso(
        scope_queryset_to_school(Nota.objects.all(), active_school),
        curso_norm,
        school=active_school,
        school_course=school_course,
    ).filter(materia=materia)
    notas_qs = _apply_cuatrimestre_filter(notas_qs, cuatrimestre)

    notas_payload = _build_notas_payload(notas_qs)

    payload = {
        "scope": "materia_curso",
        "rol": role,
        **_public_course_payload(school=active_school, course_code=curso_norm, school_course=school_course),
        "materia": {"id": id_materia, "nombre": materia},
        "filtros": {"cuatrimestre": cuatrimestre},
        "permisos": {"cursos_habilitados": cursos_habilitados},
        **notas_payload,
    }
    cache.set(cache_key, payload, 120)
    return Response(payload)
