from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .jwt_auth import CookieJWTAuthentication
from .models import Alumno, InvitadoReunion, Mensaje, Notificacion, Reunion
from .models_preceptores import PreceptorCurso, ProfesorCurso, SchoolMembership
from .schools import get_request_school
from .user_groups import get_user_group_names
from .api_mensajes._helpers import _notify_msg

User = get_user_model()
STAFF_ROLES = {"Preceptores", "Profesores", "EOE", "Integracion", "Directivos"}


def _can_organize(user, alumno):
    if user.is_superuser:
        return True
    if not user.groups.filter(name="Preceptores").exists():
        return False
    return PreceptorCurso.objects.filter(
        preceptor=user, school=alumno.school, school_course=alumno.school_course
    ).exists()


def _staff_users(school):
    ids = set(SchoolMembership.objects.filter(school=school, is_active=True).values_list("user_id", flat=True))
    ids.update(PreceptorCurso.objects.filter(school=school).values_list("preceptor_id", flat=True))
    ids.update(ProfesorCurso.objects.filter(school=school).values_list("profesor_id", flat=True))
    return User.objects.filter(id__in=ids, is_active=True, groups__name__in=STAFF_ROLES).distinct().order_by("last_name", "first_name", "username")


def _parse_start(value):
    dt = parse_datetime(str(value or ""))
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _parse_boundary(value):
    parsed = _parse_start(value)
    if parsed:
        return parsed
    day = parse_date(str(value or ""))
    return timezone.make_aware(datetime.combine(day, time.min)) if day else None


def _student(school, value):
    try:
        student_id = int(value)
    except (TypeError, ValueError):
        return None
    return Alumno.objects.filter(school=school, pk=student_id).select_related("padre", "school_course").first()


def _schedule(data):
    start = _parse_start(data.get("inicio"))
    try:
        duration = int(data.get("duracion_minutos", 30))
    except (TypeError, ValueError):
        duration = 0
    modality = str(data.get("modalidad") or "presencial").strip()
    place = str(data.get("lugar") or "").strip()
    reason = str(data.get("motivo") or "").strip()
    if not start or start <= timezone.now():
        return None, "Elegí una fecha y hora futuras."
    if duration < 15 or duration > 180:
        return None, "La duración debe estar entre 15 y 180 minutos."
    if modality not in {"presencial", "virtual"}:
        return None, "Modalidad inválida."
    if (modality == "virtual" and not place) or len(place) > 255 or not reason or len(reason) > 500:
        return None, "Completá el motivo y, si es virtual, el enlace."
    return dict(inicio=start, duracion_minutos=duration, modalidad=modality, lugar=place, motivo=reason), None


def _serialize(meeting, user):
    invite = next((i for i in meeting.invitados.all() if i.usuario_id == user.id), None)
    is_organizer = meeting.organizador_id == user.id
    is_family = meeting.familiar_id == user.id
    result = {
        "id": meeting.id,
        "alumno_id": meeting.alumno_id,
        "alumno_nombre": str(meeting.alumno),
        "inicio": meeting.inicio,
        "duracion_minutos": meeting.duracion_minutos,
        "modalidad": meeting.modalidad,
        "lugar": meeting.lugar,
        "motivo": meeting.motivo,
        "estado": meeting.estado,
        "organizador": meeting.organizador.get_full_name() or meeting.organizador.username,
        "confirmado_en": meeting.respuesta_familiar_en if is_family else (invite.confirmado_en if invite else None),
        "nota_familiar": meeting.nota_familiar if is_family or is_organizer else "",
        "puede_editar": is_organizer,
        "puede_responder": is_family or invite is not None,
        "es_familiar": is_family,
    }
    if is_organizer:
        result["familiar"] = meeting.familiar.get_full_name() or meeting.familiar.username
        result["respuesta_familiar_en"] = meeting.respuesta_familiar_en
        result["invitados"] = [
            {"id": i.usuario_id, "nombre": i.usuario.get_full_name() or i.usuario.username,
             "confirmado_en": i.confirmado_en} for i in meeting.invitados.all()
        ]
    return result


def _notify(meeting, users, title):
    for user in users:
        Notificacion.objects.create(
            school=meeting.school, destinatario=user, tipo="evento", titulo=title,
            descripcion=f"{meeting.alumno}: {meeting.inicio.astimezone(timezone.get_current_timezone()).strftime('%d/%m/%Y %H:%M')}",
            url=f"/calendario?reunion={meeting.id}", meta={"reunion_id": meeting.id, "alumno_id": meeting.alumno_id},
        )


def _get_meeting(request, pk):
    school = get_request_school(request)
    meeting = Reunion.objects.filter(school=school, pk=pk).select_related(
        "alumno", "organizador", "familiar", "school"
    ).prefetch_related("invitados__usuario").first()
    if not meeting:
        return None
    user_id = request.user.id
    if user_id not in {meeting.organizador_id, meeting.familiar_id} and not any(
        i.usuario_id == user_id for i in meeting.invitados.all()
    ):
        return None
    return meeting


@api_view(["GET"])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated])
def meeting_options(request):
    school = get_request_school(request)
    alumno = _student(school, request.GET.get("alumno_id"))
    if not alumno or not _can_organize(request.user, alumno):
        return Response({"detail": "No autorizado para este alumno."}, status=403)
    family = alumno.padre
    return Response({
        "alumno": {"id": alumno.id, "nombre": str(alumno)},
        "familiar": {"id": family.id, "nombre": family.get_full_name() or family.username} if family and family.is_active else None,
        "personal": [
            {"id": u.id, "nombre": u.get_full_name() or u.username,
             "roles": sorted(STAFF_ROLES.intersection(get_user_group_names(u)))}
            for u in _staff_users(school) if u.id != request.user.id
        ],
    })


@api_view(["GET", "POST"])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated])
def meetings(request):
    school = get_request_school(request)
    if request.method == "GET":
        qs = Reunion.objects.filter(school=school).filter(
            Q(organizador=request.user) | Q(familiar=request.user) | Q(invitados__usuario=request.user)
        ).distinct().select_related("alumno", "organizador", "familiar").prefetch_related("invitados__usuario")
        start = _parse_boundary(request.GET.get("desde"))
        end = _parse_boundary(request.GET.get("hasta"))
        if start:
            qs = qs.filter(inicio__gte=start - timedelta(hours=3))
        if end:
            qs = qs.filter(inicio__lt=end)
        return Response([_serialize(m, request.user) for m in qs[:300]])

    alumno = _student(school, request.data.get("alumno_id"))
    if not alumno or not _can_organize(request.user, alumno):
        return Response({"detail": "No autorizado para este alumno."}, status=403)
    if not alumno.padre_id or not alumno.padre.is_active:
        return Response({"detail": "Este alumno no tiene un familiar activo vinculado."}, status=400)
    schedule, error = _schedule(request.data)
    if error:
        return Response({"detail": error}, status=400)
    raw_ids = request.data.get("invitados_ids") or []
    if not isinstance(raw_ids, list) or len(raw_ids) > 30:
        return Response({"detail": "Invitados inválidos."}, status=400)
    try:
        ids = {int(item) for item in raw_ids}
    except (TypeError, ValueError):
        return Response({"detail": "Invitados inválidos."}, status=400)
    if request.user.id in ids or alumno.padre_id in ids:
        return Response({"detail": "El organizador y la familia ya participan de la reunión."}, status=400)
    staff = list(_staff_users(school).filter(id__in=ids))
    if len(staff) != len(ids):
        return Response({"detail": "Hay invitados que no pertenecen al personal de este colegio."}, status=400)

    with transaction.atomic():
        meeting = Reunion.objects.create(
            school=school, alumno=alumno, organizador=request.user, familiar=alumno.padre, **schedule
        )
        message = Mensaje.objects.create(
            school=school, school_course=alumno.school_course, alumno=alumno,
            curso=alumno.school_course.code, remitente=request.user, destinatario=alumno.padre,
            tipo_remitente="Preceptor", asunto="Invitación a reunión",
            contenido=f"Te invitamos a una reunión por {alumno.nombre}. Confirmá o solicitá otro horario desde esta invitación.",
        )
        meeting.mensaje_familia = message
        meeting.save(update_fields=["mensaje_familia", "actualizada_en"])
        InvitadoReunion.objects.bulk_create([InvitadoReunion(reunion=meeting, usuario=u) for u in staff])
        _notify(meeting, staff, "Invitación a reunión")
        transaction.on_commit(lambda: _notify_msg(msg=message, receptor=alumno.padre, alumno=alumno, actor=request.user))
    meeting = _get_meeting(request, meeting.id)
    return Response({**_serialize(meeting, request.user), "mensaje_id": message.id}, status=201)


@api_view(["GET", "PATCH"])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated])
def meeting_detail(request, pk):
    meeting = _get_meeting(request, pk)
    if not meeting:
        return Response({"detail": "Reunión no encontrada."}, status=404)
    if request.method == "GET":
        return Response(_serialize(meeting, request.user))
    if request.user.id != meeting.organizador_id:
        return Response({"detail": "Solo el organizador puede modificar la reunión."}, status=403)
    if meeting.estado == "cancelada":
        return Response({"detail": "La reunión está cancelada."}, status=400)
    if request.data.get("cancelar") is True:
        meeting.estado = "cancelada"
        meeting.save(update_fields=["estado", "actualizada_en"])
        _notify(meeting, [meeting.familiar, *[i.usuario for i in meeting.invitados.all()]], "Reunión cancelada")
        return Response(_serialize(meeting, request.user))
    schedule, error = _schedule(request.data)
    if error:
        return Response({"detail": error}, status=400)
    with transaction.atomic():
        for key, value in schedule.items():
            setattr(meeting, key, value)
        meeting.estado = "pendiente"
        meeting.respuesta_familiar_en = None
        meeting.nota_familiar = ""
        meeting.save()
        meeting.invitados.update(confirmado_en=None)
        _notify(meeting, [meeting.familiar, *[i.usuario for i in meeting.invitados.all()]], "Nuevo horario de reunión")
    return Response(_serialize(_get_meeting(request, pk), request.user))


@api_view(["POST"])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated])
def meeting_reply(request, pk):
    meeting = _get_meeting(request, pk)
    if not meeting:
        return Response({"detail": "Reunión no encontrada."}, status=404)
    if meeting.estado == "cancelada":
        return Response({"detail": "La reunión está cancelada."}, status=400)
    action = request.data.get("accion")
    if request.user.id == meeting.familiar_id:
        if action not in {"confirmar", "solicitar_cambio"}:
            return Response({"detail": "Respuesta inválida."}, status=400)
        meeting.estado = "confirmada" if action == "confirmar" else "cambio_solicitado"
        meeting.respuesta_familiar_en = timezone.now()
        meeting.nota_familiar = str(request.data.get("nota") or "").strip()[:500] if action == "solicitar_cambio" else ""
        meeting.save(update_fields=["estado", "respuesta_familiar_en", "nota_familiar", "actualizada_en"])
        _notify(meeting, [meeting.organizador], "Reunión confirmada" if action == "confirmar" else "Cambio de horario solicitado")
    elif action == "confirmar":
        invite = next((i for i in meeting.invitados.all() if i.usuario_id == request.user.id), None)
        if not invite:
            return Response({"detail": "No autorizado."}, status=403)
        invite.confirmado_en = timezone.now()
        invite.save(update_fields=["confirmado_en"])
        _notify(meeting, [meeting.organizador], "Invitado confirmó la reunión")
    else:
        return Response({"detail": "Respuesta inválida."}, status=400)
    return Response(_serialize(_get_meeting(request, pk), request.user))


@api_view(["POST"])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated])
def meeting_reminder(request, pk):
    meeting = _get_meeting(request, pk)
    if not meeting:
        return Response({"detail": "Reunión no encontrada."}, status=404)
    if meeting.organizador_id != request.user.id:
        return Response({"detail": "No autorizado."}, status=403)
    if meeting.estado == "cancelada":
        return Response({"detail": "La reunión está cancelada."}, status=400)
    pending = [i.usuario for i in meeting.invitados.all() if not i.confirmado_en]
    if meeting.respuesta_familiar_en is None:
        pending.append(meeting.familiar)
    if pending:
        _notify(meeting, pending, "Recordatorio de reunión pendiente")
    return Response({"enviados": len(pending)})
