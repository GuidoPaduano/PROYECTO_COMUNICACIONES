# calificaciones/api_mensajes_alumno.py
from __future__ import annotations

from typing import Optional

from django.contrib.auth.models import User
from django.core.exceptions import FieldDoesNotExist
from django.db import transaction
from django.utils import timezone

from rest_framework.decorators import api_view, authentication_classes, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.response import Response

from .models import Alumno, Mensaje, Notificacion


# =========================================================
# Helpers
# =========================================================
PROF_GROUPS = ["Profesor", "Profesores", "Docente", "Docentes"]
PREC_GROUPS = ["Preceptor", "Preceptores"]


def _has_field(model, field_name: str) -> bool:
    try:
        model._meta.get_field(field_name)
        return True
    except FieldDoesNotExist:
        return False


def _sender_field() -> str:
    """Compat: Mensaje.remitente (nuevo) vs Mensaje.emisor (viejo)."""
    return "remitente" if _has_field(Mensaje, "remitente") else "emisor"


def _recipient_field() -> str:
    """Compat: Mensaje.destinatario (nuevo) vs Mensaje.receptor (viejo)."""
    return "destinatario" if _has_field(Mensaje, "destinatario") else "receptor"


def _curso_field() -> str:
    """Compat: Mensaje.curso_asociado (viejo) vs Mensaje.curso (nuevo)."""
    if _has_field(Mensaje, "curso_asociado"):
        return "curso_asociado"
    if _has_field(Mensaje, "curso"):
        return "curso"
    return ""


def _user_to_dict(u: User, grupo_hint: str = ""):
    nombre = (u.get_full_name() or u.username or f"usuario-{u.id}").strip()
    return {
        "id": u.id,
        "nombre": nombre,
        "username": u.username,
        "grupo": grupo_hint or (u.groups.first().name if u.groups.exists() else ""),
    }


def _infer_alumno_for_user(user: User) -> Optional[Alumno]:
    """Intenta inferir el Alumno asociado a este user (usuario o padre)."""
    try:
        a = Alumno.objects.filter(usuario=user).first() if _has_field(Alumno, "usuario") else None
        if a:
            return a
    except Exception:
        pass

    try:
        a = Alumno.objects.filter(padre=user).first()
        if a:
            return a
    except Exception:
        pass

    # Heurística legacy por nombre
    try:
        full = (user.get_full_name() or "").strip()
        if full:
            a = Alumno.objects.filter(nombre__iexact=full).first()
            if a:
                return a
    except Exception:
        pass

    return None


def _allowed_docentes_qs():
    """Por ahora: todos los Profesores/Preceptores activos."""
    return User.objects.filter(is_active=True, groups__name__in=(PROF_GROUPS + PREC_GROUPS)).distinct()


# =========================================================
# GET: destinatarios (alumno) → lista de docentes/preceptores
# =========================================================
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def docentes_destinatarios(request):
    user = request.user

    curso = (request.GET.get("curso") or "").strip()

    # Si no nos pasaron curso, tratamos de inferirlo del alumno logueado
    if not curso:
        alum = _infer_alumno_for_user(user)
        if alum and getattr(alum, "curso", None):
            curso = alum.curso

    qs = _allowed_docentes_qs()

    profs = qs.filter(groups__name__in=PROF_GROUPS).distinct()
    precs = qs.filter(groups__name__in=PREC_GROUPS).distinct()

    return Response(
        {
            "curso": curso or "",
            "profesores": [_user_to_dict(u, "Profesor") for u in profs],
            "preceptores": [_user_to_dict(u, "Preceptor") for u in precs],
            "results": [_user_to_dict(u) for u in qs],
        },
        status=200,
    )


# =========================================================
# POST: enviar (alumno → docente/preceptor)
# =========================================================
@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def alumno_enviar(request):
    """
    Cuerpo esperado:
    {
        "receptor_id": 123,     // obligatorio
        "asunto": "Consulta",   // obligatorio
        "contenido": "Hola...", // obligatorio
        "curso": "1A"           // opcional (si podemos, lo inferimos de Alumno)
    }
    """
    user = request.user
    data = request.data or {}

    receptor_id = data.get("receptor_id")
    asunto = (data.get("asunto") or "").strip()
    contenido = (data.get("contenido") or "").strip()
    curso = (data.get("curso") or "").strip()

    if not receptor_id or not asunto or not contenido:
        return Response(
            {"detail": "Faltan datos: receptor_id, asunto y contenido son obligatorios."},
            status=400,
        )

    # Validar receptor
    try:
        receptor = User.objects.get(id=receptor_id, is_active=True)
    except User.DoesNotExist:
        return Response({"detail": "El destinatario no existe."}, status=404)

    grupos_receptor = set(receptor.groups.values_list("name", flat=True))
    if not (grupos_receptor.intersection(PROF_GROUPS) or grupos_receptor.intersection(PREC_GROUPS)):
        return Response({"detail": "El destinatario no es Profesor/Preceptor habilitado."}, status=403)

    # Inferir curso y alumno, si se puede
    alumno = None
    if not curso:
        alumno = _infer_alumno_for_user(user)
        if alumno and getattr(alumno, "curso", None):
            curso = alumno.curso
    else:
        alumno = _infer_alumno_for_user(user)

    sf = _sender_field()
    rf = _recipient_field()
    cf = _curso_field()

    kwargs = {
        sf: user,
        rf: receptor,
        "asunto": asunto[:255],
        "contenido": contenido,
    }

    if cf and curso:
        kwargs[cf] = curso

    if _has_field(Mensaje, "alumno") and alumno is not None:
        kwargs["alumno"] = alumno

    if _has_field(Mensaje, "fecha_envio"):
        kwargs["fecha_envio"] = timezone.now()

    with transaction.atomic():
        msg = Mensaje.objects.create(**kwargs)

    # Notificacion campanita para el docente/preceptor receptor
    try:
        contenido_corto = (contenido[:160] + "...") if len(contenido) > 160 else contenido
        url = "/mensajes"
        if hasattr(msg, "thread_id") and getattr(msg, "thread_id", None):
            url = f"/mensajes/hilo/{getattr(msg, 'thread_id')}"
        actor_label = (user.get_full_name() or user.username or "Usuario").strip()
        titulo = f"{actor_label}: {asunto}" if asunto else f"Nuevo mensaje de {actor_label}"
        Notificacion.objects.create(
            destinatario=receptor,
            tipo="mensaje",
            titulo=titulo,
            descripcion=contenido_corto.strip() or None,
            url=url,
            leida=False,
            meta={
                "mensaje_id": getattr(msg, "id", None),
                "thread_id": str(getattr(msg, "thread_id", "")) if hasattr(msg, "thread_id") else str(getattr(msg, "id", "")),
                "curso": curso or "",
                "remitente_id": getattr(user, "id", None),
                "alumno_id": getattr(alumno, "id", None) if alumno else None,
            },
        )
    except Exception:
        pass

    # Respuesta compatible (front suele esperar emisor/receptor)
    return Response(
        {
            "ok": True,
            "id": msg.id,
            "asunto": getattr(msg, "asunto", ""),
            "contenido": getattr(msg, "contenido", ""),
            "curso": curso or "",
            "fecha_envio": getattr(msg, "fecha_envio", None),
            "emisor": _user_to_dict(user),
            "receptor": _user_to_dict(receptor),
            "emisor_id": getattr(user, "id", None),
            "receptor_id": getattr(receptor, "id", None),
        },
        status=201,
    )
