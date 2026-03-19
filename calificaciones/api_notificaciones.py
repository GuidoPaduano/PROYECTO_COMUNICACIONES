# calificaciones/api_notificaciones.py
from __future__ import annotations

from django.views.decorators.csrf import csrf_exempt
from django.db import models
from django.utils import timezone

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .jwt_auth import CookieJWTAuthentication as JWTAuthentication

from .models import Notificacion


def _parse_int(value, default=None):
    try:
        return int(value)
    except Exception:
        return default


def _parse_limit(request, default=5, max_limit=12):
    lim = _parse_int(request.GET.get("limit"), default)
    if lim is None:
        lim = default
    lim = max(1, min(lim, max_limit))
    return lim


def _serialize_notif(n: Notificacion):
    return {
        "id": n.id,
        "tipo": n.tipo,
        "titulo": n.titulo,
        "descripcion": n.descripcion or "",
        "url": n.url or "",
        "creada_en": n.creada_en.isoformat() if getattr(n, "creada_en", None) else None,
        "leida": bool(n.leida),
        "meta": n.meta or {},
    }


@csrf_exempt
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def notificaciones_unread_count(request):
    user = request.user
    count = Notificacion.objects.filter(destinatario=user, leida=False).count()
    return Response({"count": count}, status=200)


@csrf_exempt
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def notificaciones_recientes(request):
    user = request.user
    qs = Notificacion.objects.filter(destinatario=user)

    if request.GET.get("solo_no_leidas") in ("1", "true", "True"):
        qs = qs.filter(leida=False)

    lim = _parse_limit(request, default=5, max_limit=12)
    rows = list(
        qs.order_by("-creada_en", "-id")
        .values("id", "tipo", "titulo", "descripcion", "url", "creada_en", "leida", "meta")[:lim]
    )
    data = [
        {
            "id": r["id"],
            "tipo": r["tipo"],
            "titulo": r["titulo"],
            "descripcion": r.get("descripcion") or "",
            "url": r.get("url") or "",
            "creada_en": r["creada_en"].isoformat() if r.get("creada_en") else None,
            "leida": bool(r.get("leida")),
            "meta": r.get("meta") or {},
        }
        for r in rows
    ]
    return Response(data, status=200)


@csrf_exempt
@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def notificaciones_marcar_leida(request, notif_id: int):
    user = request.user
    updated = Notificacion.objects.filter(destinatario=user, id=notif_id, leida=False).update(leida=True)
    return Response({"success": True, "updated": int(updated)}, status=200)


@csrf_exempt
@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def notificaciones_marcar_todas_leidas(request):
    user = request.user
    updated = Notificacion.objects.filter(destinatario=user, leida=False).update(leida=True)
    return Response({"success": True, "updated": int(updated)}, status=200)
