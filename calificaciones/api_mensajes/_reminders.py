from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from ..jwt_auth import CookieJWTAuthentication
from ..models import Mensaje, Notificacion
from ..message_reminders import with_reply_status
from ..schools import get_request_school, get_requested_school_identifier, get_school_by_identifier
from ..ws_notify import push_unread_update_for_notification
from ._helpers import _notif_url_for_msg


@api_view(['POST'])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated])
def message_reminder(request, mensaje_id):
    school = get_request_school(request)
    requested = get_requested_school_identifier(request)
    if school is None:
        return Response({'detail': 'No autorizado para este colegio.' if requested else 'Seleccioná un colegio.'}, status=403 if requested else 400)
    if requested:
        selected = get_school_by_identifier(requested)
        if selected is None or selected.pk != school.pk:
            return Response({'detail': 'No autorizado para este colegio.'}, status=403)
    data = request.data or {}
    if not isinstance(data, dict) or data.get('accion', 'recordar') not in {'recordar', 'resolver'}:
        return Response({'detail': 'Acción inválida.'}, status=400)
    action = data.get('accion', 'recordar')
    with transaction.atomic():
        msg = with_reply_status(Mensaje.objects.select_for_update()).filter(pk=mensaje_id, school=school, remitente=request.user).first()
        if msg is None:
            return Response({'detail': 'Mensaje enviado no encontrado.'}, status=404)
        now = timezone.now()
        if action == 'resolver':
            if not msg.recordatorio_resuelto_en:
                msg.recordatorio_resuelto_en = now
                msg.save(update_fields=['recordatorio_resuelto_en'])
            return Response({'detail': 'Mensaje marcado como resuelto.', 'recordatorio_resuelto_en': msg.recordatorio_resuelto_en})
        if msg.recordatorio_resuelto_en or msg.recordatorio_respondido:
            return Response({'detail': 'El mensaje ya fue respondido o marcado como resuelto.', 'recordatorio_respondido': msg.recordatorio_respondido, 'recordatorio_resuelto_en': msg.recordatorio_resuelto_en}, status=409)
        if msg.remitente_id == msg.destinatario_id or not msg.destinatario.is_active:
            return Response({'detail': 'No se puede enviar un recordatorio a ese destinatario.'}, status=400)
        if msg.ultimo_recordatorio_en and now < msg.ultimo_recordatorio_en + timedelta(hours=24):
            return Response({'detail': 'Ya enviaste un recordatorio. Podés enviar otro después de 24 horas.', 'ultimo_recordatorio_en': msg.ultimo_recordatorio_en}, status=429)
        label = request.user.get_full_name() or request.user.username
        notif = Notificacion.objects.create(
            school=school, destinatario=msg.destinatario, tipo='mensaje',
            titulo=f'Recordatorio de {label}'[:255],
            descripcion='Tenés un mensaje pendiente de respuesta. Abrí la conversación para revisarlo.',
            url=_notif_url_for_msg(msg),
            meta={'mensaje_id':msg.id, 'recordatorio':True, 'alumno_id':msg.alumno_id, 'remitente_id':msg.remitente_id},
        )
        msg.ultimo_recordatorio_en = now
        msg.save(update_fields=['ultimo_recordatorio_en'])
        transaction.on_commit(lambda: push_unread_update_for_notification(notif))
    return Response({'detail': 'Recordatorio enviado.', 'ultimo_recordatorio_en': now}, status=201)
