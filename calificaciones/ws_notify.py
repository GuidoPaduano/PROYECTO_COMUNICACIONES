"""
Helper para enviar actualizaciones de contadores via WebSocket (Django Channels).
Se usa desde signals, tasks y views al crear notificaciones o mensajes.
"""
from asgiref.sync import async_to_sync


def push_unread_update(user_id: int, messages: int | None = None, notifications: int | None = None) -> None:
    """Envía contadores actualizados al cliente WebSocket del usuario."""
    try:
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return

        data = {}
        if messages is not None:
            data["messages"] = messages
        if notifications is not None:
            data["notifications"] = notifications
        if not data:
            return

        async_to_sync(channel_layer.group_send)(
            f"notif_user_{user_id}",
            {"type": "notification.update", "data": data},
        )
    except Exception:
        pass


def push_unread_update_for_notification(notificacion) -> None:
    """Notifica a un destinatario cuando se crea una Notificacion."""
    try:
        dest = getattr(notificacion, "destinatario", None)
        if dest is None:
            return
        from .models import Notificacion
        count = Notificacion.objects.filter(destinatario=dest, leida=False).count()
        push_unread_update(user_id=dest.pk, notifications=count)
    except Exception:
        pass


def push_unread_update_for_message(mensaje, recipient) -> None:
    """Notifica a un receptor cuando se crea un Mensaje no leído."""
    try:
        from .models import Mensaje
        rf = "destinatario" if hasattr(Mensaje, "destinatario") else "receptor"
        count = Mensaje.objects.filter(**{rf: recipient, "leido": False}).count()
        push_unread_update(user_id=recipient.pk, messages=count)
    except Exception:
        pass
