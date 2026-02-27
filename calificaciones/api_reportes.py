from __future__ import annotations

from typing import Optional

from django.core.cache import cache
from django.db.models import Avg, Count, FloatField, Q, Value
from django.db.models.functions import Cast, Replace, TruncMonth, Trim, Upper

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from .contexto import resolve_alumno_for_user
from .models import Alumno, Asistencia, Nota

try:
    from .models_preceptores import PreceptorCurso, ProfesorCurso  # type: ignore
except Exception:
    PreceptorCurso = None
    ProfesorCurso = None


_TEXT_GRADES = {"TEA", "TEP", "TED", "NO ENTREGADO"}


def _user_groups(user) -> set[str]:
    try:
        return {str(x).strip() for x in user.groups.values_list("name", flat=True)}
    except Exception:
        return set()


def _has_group(user, *names: str) -> bool:
    groups = _user_groups(user)
    wanted = {str(x).strip() for x in names if str(x).strip()}
    return bool(groups.intersection(wanted))


def _role_label(user) -> str:
    if getattr(user, "is_superuser", False):
        return "Superuser"
    if _has_group(user, "Padres"):
        return "Padres"
    if _has_group(user, "Alumnos"):
        return "Alumnos"
    if _has_group(user, "Profesores"):
        return "Profesores"
    if _has_group(user, "Preceptores"):
        return "Preceptores"
    return "SinRol"


def _round2(value):
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except Exception:
        return None


def _empty_notas_stats() -> dict:
    return {
        "promedio_general": None,
        "promedios_por_materia": {},
        "distribucion_notas": {
            "rango_1_3": 0,
            "rango_4_6": 0,
            "rango_7_10": 0,
        },
        "evolucion_mensual": {},
    }


def _empty_asistencias_stats() -> dict:
    return {
        "totales": {
            "presente": 0,
            "ausente": 0,
            "tarde": 0,
        },
        "porcentaje_asistencia": None,
        "evolucion_mensual": {},
    }


def _normalize_curso(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""

    try:
        mapping = {str(k).strip().upper(): str(k).strip() for k, _ in getattr(Alumno, "CURSOS", [])}
    except Exception:
        mapping = {}

    mapped = mapping.get(value.upper())
    if mapped:
        return mapped

    try:
        found = (
            Alumno.objects.filter(curso__iexact=value)
            .values_list("curso", flat=True)
            .order_by("curso")
            .first()
        )
        if found:
            return str(found)
    except Exception:
        pass

    return value


def _normalize_cuatrimestre(raw: str) -> Optional[int]:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        parsed = int(value)
    except Exception:
        return None
    if parsed not in (1, 2):
        return None
    return parsed


def _serialize_alumno(a: Alumno) -> dict:
    return {
        "id": a.id,
        "id_alumno": getattr(a, "id_alumno", None),
        "nombre": getattr(a, "nombre", ""),
        "curso": getattr(a, "curso", ""),
    }


def _profesor_cursos_habilitados(user) -> tuple[list[str], str]:
    if getattr(user, "is_superuser", False):
        return sorted({x[0] for x in getattr(Alumno, "CURSOS", [])}), "superuser"

    if ProfesorCurso is not None:
        try:
            cursos = list(
                ProfesorCurso.objects.filter(profesor=user)
                .values_list("curso", flat=True)
                .distinct()
            )
            if cursos:
                return sorted(set(cursos)), "asignacion_modelo"
        except Exception:
            pass

    # Fallback 1: cursos definidos como nombre de grupo.
    valid_courses = {str(c[0]) for c in getattr(Alumno, "CURSOS", [])}
    from_groups = sorted(set(_user_groups(user)).intersection(valid_courses))
    if from_groups:
        return from_groups, "grupos_curso"

    # Fallback 2: comportamiento legacy del proyecto (si no hay asignaciones, permite todos).
    return sorted(valid_courses), "fallback_todos"


def _preceptor_cursos_habilitados(user) -> tuple[list[str], str]:
    if getattr(user, "is_superuser", False):
        return sorted({x[0] for x in getattr(Alumno, "CURSOS", [])}), "superuser"

    if PreceptorCurso is not None:
        try:
            cursos = list(
                PreceptorCurso.objects.filter(preceptor=user)
                .values_list("curso", flat=True)
                .distinct()
            )
            if cursos:
                return sorted(set(cursos)), "asignacion_modelo"
        except Exception:
            pass

    # Fallback legacy usado en otras partes del proyecto.
    hardcoded = {
        "preceptor1": "1A",
        "preceptor2": "3B",
        "preceptor3": "5NAT",
    }
    mapped = hardcoded.get(getattr(user, "username", ""))
    if mapped:
        return [mapped], "fallback_usuario"

    valid_courses = {str(c[0]) for c in getattr(Alumno, "CURSOS", [])}
    from_groups = sorted(set(_user_groups(user)).intersection(valid_courses))
    if from_groups:
        return from_groups, "grupos_curso"

    return [], "sin_asignaciones"


def _filter_numeric_notas(qs):
    # Nota.calificacion es CharField y puede contener TEA/TEP/TED/NO ENTREGADO.
    # Para agregados numericos limpiamos y casteamos solo valores no textuales.
    cleaned = qs.annotate(calificacion_texto=Upper(Trim("calificacion"))).exclude(
        calificacion_texto__in=_TEXT_GRADES
    )
    return cleaned.annotate(
        calificacion_num=Cast(
            Replace(Trim("calificacion"), Value(","), Value(".")),
            FloatField(),
        )
    ).filter(
        calificacion_num__isnull=False,
        calificacion_num__gte=1,
        calificacion_num__lte=10,
    )


def _build_notas_stats(base_qs):
    numeric = _filter_numeric_notas(base_qs)

    promedio_general = numeric.aggregate(value=Avg("calificacion_num")).get("value")

    por_materia_rows = (
        numeric.values("materia")
        .annotate(promedio=Avg("calificacion_num"))
        .order_by("materia")
    )
    promedios_por_materia = {
        str(row["materia"]): _round2(row["promedio"])
        for row in por_materia_rows
    }

    distribucion = numeric.aggregate(
        rango_1_3=Count("id", filter=Q(calificacion_num__gte=1, calificacion_num__lt=4)),
        rango_4_6=Count("id", filter=Q(calificacion_num__gte=4, calificacion_num__lt=7)),
        rango_7_10=Count("id", filter=Q(calificacion_num__gte=7, calificacion_num__lte=10)),
    )

    evolucion_rows = (
        numeric.annotate(mes=TruncMonth("fecha"))
        .values("mes")
        .annotate(promedio=Avg("calificacion_num"))
        .order_by("mes")
    )
    evolucion = {}
    for row in evolucion_rows:
        mes = row.get("mes")
        if not mes:
            continue
        evolucion[mes.strftime("%Y-%m")] = _round2(row.get("promedio"))

    return {
        "promedio_general": _round2(promedio_general),
        "promedios_por_materia": promedios_por_materia,
        "distribucion_notas": {
            "rango_1_3": int(distribucion.get("rango_1_3") or 0),
            "rango_4_6": int(distribucion.get("rango_4_6") or 0),
            "rango_7_10": int(distribucion.get("rango_7_10") or 0),
        },
        "evolucion_mensual": evolucion,
    }


def _build_asistencias_stats(base_qs):
    totals = base_qs.aggregate(
        total_presente=Count("id", filter=Q(presente=True, tarde=False)),
        total_ausente=Count("id", filter=Q(presente=False)),
        total_tarde=Count("id", filter=Q(tarde=True)),
    )

    presente = int(totals.get("total_presente") or 0)
    ausente = int(totals.get("total_ausente") or 0)
    tarde = int(totals.get("total_tarde") or 0)
    total = presente + ausente + tarde

    porcentaje = None
    if total > 0:
        porcentaje = _round2(((presente + tarde) / total) * 100)

    evolucion_rows = (
        base_qs.annotate(mes=TruncMonth("fecha"))
        .values("mes")
        .annotate(
            ausentes=Count("id", filter=Q(presente=False)),
            tardes=Count("id", filter=Q(tarde=True)),
        )
        .order_by("mes")
    )
    evolucion = {}
    for row in evolucion_rows:
        mes = row.get("mes")
        if not mes:
            continue
        evolucion[mes.strftime("%Y-%m")] = {
            "ausentes": int(row.get("ausentes") or 0),
            "tardes": int(row.get("tardes") or 0),
        }

    return {
        "totales": {
            "presente": presente,
            "ausente": ausente,
            "tarde": tarde,
        },
        "porcentaje_asistencia": porcentaje,
        "evolucion_mensual": evolucion,
    }


def _resolve_parent_selected_alumno(alumnos_qs, raw: str) -> Optional[Alumno]:
    value = (raw or "").strip()
    if not value:
        return alumnos_qs.order_by("curso", "nombre").first()

    if value.isdigit():
        found = alumnos_qs.filter(id=int(value)).first()
        if found:
            return found

    return alumnos_qs.filter(id_alumno__iexact=value).first()


def _apply_cuatrimestre_filter(notas_qs, cuatrimestre: Optional[int]):
    if cuatrimestre in (1, 2):
        return notas_qs.filter(cuatrimestre=cuatrimestre)
    return notas_qs


def _resolve_materia(raw: str) -> Optional[str]:
    value = (raw or "").strip()
    if not value:
        return None

    choices = list(getattr(Nota, "MATERIAS", []))
    materias = [c[0] for c in choices]

    if value.isdigit():
        idx = int(value) - 1
        if 0 <= idx < len(materias):
            return str(materias[idx])

    value_low = value.lower()
    for key, label in choices:
        if str(key).lower() == value_low or str(label).lower() == value_low:
            return str(key)

    return None


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def reportes_mis_estadisticas(request):
    user = request.user
    role = _role_label(user)

    if role not in ("Alumnos", "Padres", "Superuser"):
        return Response({"detail": "No autorizado para este reporte."}, status=403)

    if role == "Superuser":
        alumno_id = (request.GET.get("alumno_id") or "").strip()
        if not alumno_id:
            return Response(
                {"detail": "Para superusuario, envia ?alumno_id=<id o legajo>."},
                status=400,
            )
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
        selected = _resolve_parent_selected_alumno(alumnos_qs, request.GET.get("alumno_id"))
        if not alumnos:
            return Response(
                {
                    "scope": "mis_estadisticas",
                    "rol": role,
                    "alumnos": [],
                    "alumno_activo": None,
                    "notas": _empty_notas_stats(),
                    "asistencias": _empty_asistencias_stats(),
                }
            )
    else:
        resolution = resolve_alumno_for_user(user)
        selected = resolution.alumno
        if not selected:
            return Response(
                {"detail": "No se pudo resolver el alumno asociado al usuario."},
                status=404,
            )
        alumnos = [selected]

    if not selected:
        return Response(
            {
                "scope": "mis_estadisticas",
                "rol": role,
                "alumnos": [_serialize_alumno(a) for a in alumnos],
                "alumno_activo": None,
                "notas": _empty_notas_stats(),
                "asistencias": _empty_asistencias_stats(),
            }
        )

    cuatrimestre = _normalize_cuatrimestre(request.GET.get("cuatrimestre"))
    notas_qs = Nota.objects.filter(alumno=selected)
    notas_qs = _apply_cuatrimestre_filter(notas_qs, cuatrimestre)
    asistencias_qs = Asistencia.objects.filter(alumno=selected)

    payload = {
        "scope": "mis_estadisticas",
        "rol": role,
        "alumnos": [_serialize_alumno(a) for a in alumnos],
        "alumno_activo": _serialize_alumno(selected),
        "filtros": {
            "cuatrimestre": cuatrimestre,
        },
        "notas": _build_notas_stats(notas_qs),
        "asistencias": _build_asistencias_stats(asistencias_qs),
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
        cursos_habilitados, modo_permiso = _profesor_cursos_habilitados(user)
    elif role == "Preceptores":
        cursos_habilitados, modo_permiso = _preceptor_cursos_habilitados(user)
    else:
        cursos_habilitados, modo_permiso = _profesor_cursos_habilitados(user)

    if cursos_habilitados and curso_norm not in set(cursos_habilitados):
        return Response({"detail": "No autorizado para ese curso."}, status=403)
    if role == "Preceptores" and not cursos_habilitados:
        return Response({"detail": "No tenes cursos asignados."}, status=403)

    cache_key = (
        f"reportes:curso:v1:u{user.id}:r{role}:c{curso_norm}:q{cuatrimestre or 'all'}"
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return Response(cached)

    notas_qs = Nota.objects.filter(alumno__curso=curso_norm)
    notas_qs = _apply_cuatrimestre_filter(notas_qs, cuatrimestre)
    asistencias_qs = Asistencia.objects.filter(alumno__curso=curso_norm)

    payload = {
        "scope": "curso",
        "rol": role,
        "curso": curso_norm,
        "filtros": {"cuatrimestre": cuatrimestre},
        "permisos": {
            "modo": modo_permiso,
            "cursos_habilitados": cursos_habilitados,
        },
        "notas": _build_notas_stats(notas_qs) if role != "Preceptores" else _empty_notas_stats(),
        "asistencias": _build_asistencias_stats(asistencias_qs),
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

    cursos_habilitados, modo_permiso = _profesor_cursos_habilitados(user)
    if cursos_habilitados and curso_norm not in set(cursos_habilitados):
        return Response({"detail": "No autorizado para ese curso."}, status=403)

    notas_qs = Nota.objects.filter(alumno__curso=curso_norm, materia=materia)
    notas_qs = _apply_cuatrimestre_filter(notas_qs, cuatrimestre)

    payload = {
        "scope": "materia_curso",
        "rol": role,
        "curso": curso_norm,
        "materia": {
            "id": id_materia,
            "nombre": materia,
        },
        "filtros": {"cuatrimestre": cuatrimestre},
        "permisos": {
            "modo": modo_permiso,
            "cursos_habilitados": cursos_habilitados,
        },
        "notas": _build_notas_stats(notas_qs),
        "asistencias": _empty_asistencias_stats(),
    }
    return Response(payload)
