import json

from django.db import IntegrityError, transaction
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..jwt_auth import CookieJWTAuthentication as JWTAuthentication
from ..models import CarpetaMensajes, ConversacionEnCarpeta, Mensaje
from ..schools import get_request_school, scope_queryset_to_school
from ._helpers import _get_curso_value


def conversation_key(message):
    """The same key for both directions of the current participant-based thread."""
    if hasattr(message, "thread_id") and message.thread_id:
        return f"thread:{message.thread_id}"
    users = sorted([message.remitente_id, message.destinatario_id])
    course = str(_get_curso_value(message) or "").strip().upper()
    return "virtual:" + json.dumps(
        [users[0], users[1], course, message.alumno_id], separators=(",", ":")
    )


def folder_assignments(messages, user, school):
    keys = {conversation_key(message) for message in messages}
    return dict(
        ConversacionEnCarpeta.objects.filter(
            school=school, usuario=user, clave__in=keys
        ).values_list("clave", "carpeta_id")
    )


def _folder_data(folder):
    return {"id": folder.id, "nombre": folder.nombre}


@api_view(["GET", "POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def folders(request):
    school = get_request_school(request)
    if school is None:
        return Response({"detail": "No hay colegio activo."}, status=400)
    qs = CarpetaMensajes.objects.filter(school=school, usuario=request.user)
    if request.method == "GET":
        return Response([_folder_data(folder) for folder in qs])
    name = str(request.data.get("nombre") or "").strip()
    if not name or len(name) > 80:
        return Response({"detail": "Escribí un nombre de hasta 80 caracteres."}, status=400)
    try:
        folder = CarpetaMensajes.objects.create(school=school, usuario=request.user, nombre=name)
    except IntegrityError:
        return Response({"detail": "Ya existe una carpeta con ese nombre."}, status=400)
    return Response(_folder_data(folder), status=201)


@api_view(["PATCH", "DELETE"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def folder_detail(request, folder_id):
    school = get_request_school(request)
    folder = CarpetaMensajes.objects.filter(
        id=folder_id, school=school, usuario=request.user
    ).first()
    if folder is None:
        return Response({"detail": "Carpeta no encontrada."}, status=404)
    if request.method == "DELETE":
        # Removing the folder returns its conversations to the main inbox.
        folder.delete()
        return Response(status=204)
    name = str(request.data.get("nombre") or "").strip()
    if not name or len(name) > 80:
        return Response({"detail": "Escribí un nombre de hasta 80 caracteres."}, status=400)
    folder.nombre = name
    try:
        folder.save(update_fields=["nombre"])
    except IntegrityError:
        return Response({"detail": "Ya existe una carpeta con ese nombre."}, status=400)
    return Response(_folder_data(folder))


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def move_conversation(request, message_id):
    school = get_request_school(request)
    message = scope_queryset_to_school(Mensaje.objects.all(), school).filter(
        id=message_id
    ).first()
    if message is None or request.user.id not in (message.remitente_id, message.destinatario_id):
        return Response({"detail": "Conversación no encontrada."}, status=404)
    if message.destinatario_id != request.user.id:
        return Response({"detail": "La conversación no está en tu bandeja."}, status=403)
    folder_id = request.data.get("carpeta_id")
    key = conversation_key(message)
    qs = ConversacionEnCarpeta.objects.filter(school=school, usuario=request.user, clave=key)
    if folder_id in (None, ""):
        qs.delete()
        return Response({"carpeta_id": None, "clave_conversacion": key})
    folder = CarpetaMensajes.objects.filter(
        id=folder_id, school=school, usuario=request.user
    ).first()
    if folder is None:
        return Response({"detail": "Carpeta no encontrada."}, status=404)
    with transaction.atomic():
        ConversacionEnCarpeta.objects.update_or_create(
            school=school, usuario=request.user, clave=key, defaults={"carpeta": folder}
        )
    return Response({"carpeta_id": folder.id, "clave_conversacion": key})
