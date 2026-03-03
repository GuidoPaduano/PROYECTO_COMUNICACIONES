from __future__ import annotations

from typing import Optional

from django.core.cache import cache
from django.db.models import Case, CharField, Count, F, Q, Value, When
from django.db.models.functions import TruncMonth, Trim, Upper

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from .contexto import resolve_alumno_for_user
from .models import Alumno, Nota

try:
    from .models_preceptores import PreceptorCurso, ProfesorCurso  # type: ignore
except Exception:
    PreceptorCurso = None
    ProfesorCurso = None

ESTADOS = ("TEA", "TEP", "TED")


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
    try:
        return {str(g).strip() for g in user.groups.values_list("name", flat=True)}
    except Exception:
        return set()


def _role_label(user) -> str:
    if getattr(user, "is_superuser", False):
        return "Superuser"
    groups = _user_groups(user)
    if "Padres" in groups:
        return "Padres"
    if "Alumnos" in groups:
        return "Alumnos"
    if "Profesores" in groups:
        return "Profesores"
    if "Preceptores" in groups:
        return "Preceptores"
    return "SinRol"


def _serialize_alumno(a: Alumno) -> dict:
    return {
        "id": a.id,
        "id_alumno": getattr(a, "id_alumno", None),
        "nombre": getattr(a, "nombre", ""),
        "curso": getattr(a, "curso", ""),
    }


def _normalize_curso(curso: str) -> str:
    raw = (curso or "").strip()
    if not raw:
        return ""

    try:
        mapping = {str(k).upper(): str(k) for k, _ in getattr(Alumno, "CURSOS", [])}
    except Exception:
        mapping = {}

    return mapping.get(raw.upper(), raw)


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


def _resolve_profesor_cursos(user) -> list[str]:
    if getattr(user, "is_superuser", False):
        return sorted({str(c[0]) for c in getattr(Alumno, "CURSOS", [])})

    if ProfesorCurso is not None:
        try:
            cursos = list(
                ProfesorCurso.objects.filter(profesor=user)
                .values_list("curso", flat=True)
                .distinct()
            )
            if cursos:
                return sorted(set(str(c) for c in cursos))
        except Exception:
            pass

    valid = {str(c[0]) for c in getattr(Alumno, "CURSOS", [])}
    from_groups = sorted(valid.intersection(_user_groups(user)))
    if from_groups:
        return from_groups

    # Fallback legacy: si no hay asignacion explicita, usar cursos existentes.
    try:
        from_db = sorted(
            {
                str(c)
                for c in Alumno.objects.exclude(curso__isnull=True)
                .exclude(curso__exact="")
                .values_list("curso", flat=True)
                .distinct()
            }
        )
        if from_db:
            return from_db
    except Exception:
        pass

    return sorted(valid)


def _resolve_preceptor_cursos(user) -> list[str]:
    if getattr(user, "is_superuser", False):
        return sorted({str(c[0]) for c in getattr(Alumno, "CURSOS", [])})

    if PreceptorCurso is not None:
        try:
            cursos = list(
                PreceptorCurso.objects.filter(preceptor=user)
                .values_list("curso", flat=True)
                .distinct()
            )
            if cursos:
                return sorted(set(str(c) for c in cursos))
        except Exception:
            pass

    valid = {str(c[0]) for c in getattr(Alumno, "CURSOS", [])}
    from_groups = sorted(valid.intersection(_user_groups(user)))
    return from_groups


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
        materia_mas_floja = sorted(
            por_materia,
            key=lambda x: (x["TEA_pct"], -x["TED_count"]),
        )[0]
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

    if role not in ("Padres", "Alumnos", "Superuser"):
        return Response({"detail": "No autorizado para este reporte."}, status=403)

    alumnos = []
    selected = None

    if role == "Superuser":
        alumno_id = (request.GET.get("alumno_id") or "").strip()
        if not alumno_id:
            return Response({"detail": "Para superusuario envia ?alumno_id=<id o legajo>."}, status=400)
        if alumno_id.isdigit():
            selected = Alumno.objects.filter(id=int(alumno_id)).first()
        else:
            selected = Alumno.objects.filter(id_alumno__iexact=alumno_id).first()
        if not selected:
            return Response({"detail": "Alumno no encontrado."}, status=404)
        alumnos = [selected]

    elif role == "Padres":
        alumnos_qs = Alumno.objects.filter(padre=user).order_by("curso", "nombre")
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
            return Response(payload)

        alumno_param = (request.GET.get("alumno_id") or "").strip()
        if not alumno_param:
            selected = alumnos[0]
        elif alumno_param.isdigit():
            selected = alumnos_qs.filter(id=int(alumno_param)).first()
        else:
            selected = alumnos_qs.filter(id_alumno__iexact=alumno_param).first()

        if not selected:
            return Response({"detail": "No autorizado para ese alumno."}, status=403)

    else:  # Alumnos
        resolution = resolve_alumno_for_user(user)
        selected = resolution.alumno
        if not selected:
            return Response({"detail": "No se pudo resolver el alumno asociado al usuario."}, status=404)
        alumnos = [selected]

    notas_qs = Nota.objects.filter(alumno=selected)
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
    return Response(payload)


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def reportes_por_curso(request, curso: str):
    user = request.user
    role = _role_label(user)
    curso_norm = _normalize_curso(curso)
    cuatrimestre = _normalize_cuatrimestre(request.GET.get("cuatrimestre"))

    if role not in ("Profesores", "Preceptores", "Superuser"):
        return Response({"detail": "No autorizado para este reporte."}, status=403)

    if role == "Profesores":
        cursos_habilitados = _resolve_profesor_cursos(user)
    elif role == "Preceptores":
        cursos_habilitados = _resolve_preceptor_cursos(user)
    else:
        cursos_habilitados = sorted({str(c[0]) for c in getattr(Alumno, "CURSOS", [])})

    # Permiso estricto: si no hay cursos asignados, se deniega.
    if not cursos_habilitados:
        return Response({"detail": "No tenes cursos asignados."}, status=403)

    if curso_norm not in set(cursos_habilitados):
        return Response({"detail": "No autorizado para ese curso."}, status=403)

    cache_key = f"reportes:v2:curso:u{user.id}:r{role}:c{curso_norm}:q{cuatrimestre or 'all'}"
    cached = cache.get(cache_key)
    if cached is not None:
        return Response(cached)

    notas_qs = Nota.objects.filter(alumno__curso=curso_norm)
    notas_qs = _apply_cuatrimestre_filter(notas_qs, cuatrimestre)

    notas_payload = _build_notas_payload(notas_qs)

    payload = {
        "scope": "curso",
        "rol": role,
        "curso": curso_norm,
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
    curso_norm = _normalize_curso(curso)
    cuatrimestre = _normalize_cuatrimestre(request.GET.get("cuatrimestre"))

    if role not in ("Profesores", "Superuser"):
        return Response({"detail": "Solo profesores pueden acceder a este reporte."}, status=403)

    materia = _resolve_materia(id_materia)
    if not materia:
        return Response({"detail": "Materia invalida."}, status=404)

    if role != "Superuser":
        cursos_habilitados = _resolve_profesor_cursos(user)
        if not cursos_habilitados:
            return Response({"detail": "No tenes cursos asignados."}, status=403)
        if curso_norm not in set(cursos_habilitados):
            return Response({"detail": "No autorizado para ese curso."}, status=403)
    else:
        cursos_habilitados = sorted({str(c[0]) for c in getattr(Alumno, "CURSOS", [])})

    notas_qs = Nota.objects.filter(alumno__curso=curso_norm, materia=materia)
    notas_qs = _apply_cuatrimestre_filter(notas_qs, cuatrimestre)

    notas_payload = _build_notas_payload(notas_qs)

    payload = {
        "scope": "materia_curso",
        "rol": role,
        "curso": curso_norm,
        "materia": {"id": id_materia, "nombre": materia},
        "filtros": {"cuatrimestre": cuatrimestre},
        "permisos": {"cursos_habilitados": cursos_habilitados},
        **notas_payload,
    }
    return Response(payload)
