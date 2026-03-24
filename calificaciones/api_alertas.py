from __future__ import annotations

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .jwt_auth import CookieJWTAuthentication as JWTAuthentication
from django.db.models import Count, Max, Q

from .models import AlertaAcademica, AlertaInasistencia, Asistencia
from .alerts import reconciliar_alertas_academicas

try:
    from .models_preceptores import PreceptorCurso  # type: ignore
except Exception:
    PreceptorCurso = None


def _is_preceptor(user) -> bool:
    try:
        if user.groups.filter(name__in=["Preceptores", "Preceptor", "Directivos", "Directivo"]).exists():
            return True
    except Exception:
        pass
    return False


def _parse_limit(request, default=20, max_limit=100):
    try:
        val = int(request.GET.get("limit", default))
    except Exception:
        val = default
    return max(1, min(val, max_limit))


def _serialize_alumno(a):
    return {
        "id": getattr(a, "id", None),
        "id_alumno": getattr(a, "id_alumno", None),
        "nombre": getattr(a, "nombre", ""),
        "apellido": getattr(a, "apellido", ""),
        "curso": getattr(a, "curso", ""),
    }


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def preceptor_alertas_academicas(request):
    user = request.user
    if not getattr(user, "is_superuser", False) and not _is_preceptor(user):
        return Response({"detail": "No autorizado."}, status=403)

    if getattr(user, "is_superuser", False):
        cursos = None
    else:
        if PreceptorCurso is None:
            return Response({"results": [], "count": 0}, status=200)
        cursos = list(
            PreceptorCurso.objects.filter(preceptor=user)
            .values_list("curso", flat=True)
            .distinct()
        )
        if not cursos:
            return Response({"results": [], "count": 0}, status=200)

    limit = _parse_limit(request)
    reconciliar_alertas_academicas(cursos=cursos)
    base_qs = AlertaAcademica.objects.filter(estado="activa")
    if cursos is not None:
        base_qs = base_qs.filter(alumno__curso__in=cursos)

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
        .select_related("alumno")
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
    if not getattr(user, "is_superuser", False) and not _is_preceptor(user):
        return Response({"detail": "No autorizado."}, status=403)

    if getattr(user, "is_superuser", False):
        cursos = None
    else:
        if PreceptorCurso is None:
            return Response({"results": [], "count": 0}, status=200)
        cursos = list(
            PreceptorCurso.objects.filter(preceptor=user)
            .values_list("curso", flat=True)
            .distinct()
        )
        if not cursos:
            return Response({"results": [], "count": 0}, status=200)

    limit = _parse_limit(request)
    base_qs = AlertaInasistencia.objects.filter(estado="activa")
    if cursos is not None:
        base_qs = base_qs.filter(curso__in=cursos)

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
        .select_related("alumno")
        .order_by("-creada_en", "-id")
    )

    alumno_ids = list(
        set(top_alumno_ids)
    )
    totales_por_alumno = {}
    if alumno_ids:
        rows = (
            Asistencia.objects.filter(
                alumno_id__in=alumno_ids,
                tipo_asistencia="clases",
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
