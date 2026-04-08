from __future__ import annotations

from django.core.cache import cache
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .jwt_auth import CookieJWTAuthentication as JWTAuthentication
from django.db.models import Count, Max, Q

from .course_access import build_course_membership_q_for_refs, get_assignment_course_refs
from .models import AlertaAcademica, AlertaInasistencia, Asistencia
from .alerts import reconciliar_alertas_academicas
from .schools import get_request_school, scope_queryset_to_school
from .user_groups import user_in_groups

try:
    from .models_preceptores import PreceptorCurso  # type: ignore
except Exception:
    PreceptorCurso = None


def _active_school_id(school) -> str:
    sid = getattr(school, "id", None)
    return str(sid) if sid is not None else "none"


def _is_preceptor(user) -> bool:
    return user_in_groups(user, "Preceptores", "Preceptor", "Directivos", "Directivo")


def _parse_limit(request, default=20, max_limit=100):
    try:
        val = int(request.GET.get("limit", default))
    except Exception:
        val = default
    return max(1, min(val, max_limit))


def _serialize_alumno(a):
    school_course = getattr(a, "school_course", None)
    return {
        "id": getattr(a, "id", None),
        "id_alumno": getattr(a, "id_alumno", None),
        "nombre": getattr(a, "nombre", ""),
        "apellido": getattr(a, "apellido", ""),
        "school_course_id": getattr(a, "school_course_id", None),
        "school_course_name": getattr(school_course, "name", None)
        or getattr(school_course, "code", None)
        or getattr(a, "curso", ""),
    }


def _assignment_alert_filter(*, refs, school_course_field: str, course_code_field: str, school_field: str | None = None):
    return build_course_membership_q_for_refs(
        refs,
        school_course_field=school_course_field,
        code_field=course_code_field,
        school_field=school_field,
    )


def _resolve_preceptor_course_refs(user, school=None):
    if getattr(user, "is_superuser", False) or PreceptorCurso is None:
        return []

    school_id = getattr(school, "id", None) or 0
    attr_name = "_cached_alertas_preceptor_refs_by_school"
    cached_attr = getattr(user, attr_name, None)
    if isinstance(cached_attr, dict) and school_id in cached_attr:
        return list(cached_attr[school_id])

    cache_key = f"alertas:v1:preceptor_refs:u{getattr(user, 'id', 'x')}:s{_active_school_id(school)}"
    cached_refs = cache.get(cache_key)
    if cached_refs is not None:
        try:
            if not isinstance(cached_attr, dict):
                cached_attr = {}
            cached_attr[school_id] = tuple(cached_refs)
            setattr(user, attr_name, cached_attr)
        except Exception:
            pass
        return list(cached_refs)

    try:
        assignments_qs = scope_queryset_to_school(PreceptorCurso.objects.filter(preceptor=user), school)
        refs = get_assignment_course_refs(assignments_qs)
    except Exception:
        refs = []

    try:
        cache.set(cache_key, tuple(refs), 180)
    except Exception:
        pass
    try:
        if not isinstance(cached_attr, dict):
            cached_attr = {}
        cached_attr[school_id] = tuple(refs)
        setattr(user, attr_name, cached_attr)
    except Exception:
        pass
    return refs


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def preceptor_alertas_academicas(request):
    user = request.user
    active_school = get_request_school(request)
    if not getattr(user, "is_superuser", False) and not _is_preceptor(user):
        return Response({"detail": "No autorizado."}, status=403)

    if getattr(user, "is_superuser", False):
        course_refs = None
    else:
        if PreceptorCurso is None:
            return Response({"results": [], "count": 0}, status=200)
        course_refs = _resolve_preceptor_course_refs(user, school=active_school)
        if not course_refs:
            return Response({"results": [], "count": 0}, status=200)

    limit = _parse_limit(request)
    reconciliar_alertas_academicas(course_refs=course_refs)
    base_qs = scope_queryset_to_school(AlertaAcademica.objects.filter(estado="activa"), active_school)
    if course_refs is not None:
        course_q = _assignment_alert_filter(
            refs=course_refs,
            school_course_field="alumno__school_course",
            course_code_field="alumno__curso",
            school_field="alumno__school",
        )
        if course_q is None:
            return Response({"results": [], "count": 0}, status=200)
        base_qs = base_qs.filter(course_q)

    top_alumno_ids = list(
        base_qs.values("alumno_id")
        .annotate(ultima_alerta=Max("creada_en"))
        .order_by("-ultima_alerta", "-alumno_id")
        .values_list("alumno_id", flat=True)[:limit]
    )
    if not top_alumno_ids:
        return Response({"results": [], "count": 0}, status=200)

    qs = (
        base_qs.filter(alumno_id__in=top_alumno_ids)
        .select_related("alumno", "alumno__school_course")
        .order_by("-creada_en", "-id")
    )

    por_alumno = {}
    for a in qs:
        alumno = getattr(a, "alumno", None)
        alumno_id = getattr(alumno, "id", None)
        if alumno_id is None:
            continue
        item = por_alumno.get(alumno_id)
        if item is None:
            por_alumno[alumno_id] = {
                "alumno": _serialize_alumno(alumno),
                "ultima_alerta": a.creada_en.isoformat() if getattr(a, "creada_en", None) else None,
                "cantidad_alertas": 1,
                "materias_en_alerta": [getattr(a, "materia", "")] if getattr(a, "materia", "") else [],
            }
        else:
            item["cantidad_alertas"] += 1
            materia = getattr(a, "materia", "")
            if materia and materia not in item["materias_en_alerta"]:
                item["materias_en_alerta"].append(materia)

    rows = list(por_alumno.values())
    rows.sort(key=lambda x: x.get("ultima_alerta") or "", reverse=True)
    rows = rows[:limit]
    return Response({"results": rows, "count": len(rows)}, status=200)


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def preceptor_alertas_inasistencias(request):
    user = request.user
    active_school = get_request_school(request)
    if not getattr(user, "is_superuser", False) and not _is_preceptor(user):
        return Response({"detail": "No autorizado."}, status=403)

    if getattr(user, "is_superuser", False):
        course_refs = None
    else:
        if PreceptorCurso is None:
            return Response({"results": [], "count": 0}, status=200)
        course_refs = _resolve_preceptor_course_refs(user, school=active_school)
        if not course_refs:
            return Response({"results": [], "count": 0}, status=200)

    limit = _parse_limit(request)
    base_qs = scope_queryset_to_school(AlertaInasistencia.objects.filter(estado="activa"), active_school)
    if course_refs is not None:
        course_q = _assignment_alert_filter(
            refs=course_refs,
            school_course_field="school_course",
            course_code_field="curso",
        )
        if course_q is None:
            return Response({"results": [], "count": 0}, status=200)
        base_qs = base_qs.filter(course_q)

    top_alumno_ids = list(
        base_qs.values("alumno_id")
        .annotate(ultima_alerta=Max("creada_en"))
        .order_by("-ultima_alerta", "-alumno_id")
        .values_list("alumno_id", flat=True)[:limit]
    )
    if not top_alumno_ids:
        return Response({"results": [], "count": 0}, status=200)

    qs = (
        base_qs.filter(alumno_id__in=top_alumno_ids)
        .select_related("alumno", "alumno__school_course")
        .order_by("-creada_en", "-id")
    )

    alumno_ids = list(
        set(top_alumno_ids)
    )
    totales_por_alumno = {}
    if alumno_ids:
        rows = (
            scope_queryset_to_school(
                Asistencia.objects.filter(
                alumno_id__in=alumno_ids,
                tipo_asistencia="clases",
                ),
                active_school,
            )
            .values("alumno_id")
            .annotate(total=Count("id", filter=Q(presente=False)))
        )
        totales_por_alumno = {
            int(r["alumno_id"]): int(r.get("total") or 0)
            for r in rows
        }

    por_alumno = {}
    for a in qs:
        alumno = getattr(a, "alumno", None)
        alumno_id = getattr(alumno, "id", None)
        if alumno_id is None:
            continue
        item = por_alumno.get(alumno_id)
        if item is None:
            por_alumno[alumno_id] = {
                "alumno": _serialize_alumno(alumno),
                "ultima_alerta": a.creada_en.isoformat() if getattr(a, "creada_en", None) else None,
                "cantidad_alertas": 1,
                "motivos": [getattr(a, "motivo", "")] if getattr(a, "motivo", "") else [],
                "valor_actual": float(getattr(a, "valor_actual", 0) or 0),
                "umbral": float(getattr(a, "umbral", 0) or 0),
                "total_inasistencias_clases": int(totales_por_alumno.get(int(alumno_id), 0)),
            }
        else:
            item["cantidad_alertas"] += 1
            motivo = getattr(a, "motivo", "")
            if motivo and motivo not in item["motivos"]:
                item["motivos"].append(motivo)

    rows = list(por_alumno.values())
    rows.sort(key=lambda x: x.get("ultima_alerta") or "", reverse=True)
    rows = rows[:limit]
    return Response({"results": rows, "count": len(rows)}, status=200)
