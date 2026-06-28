"""
WebSocket consumer para notificaciones en tiempo real.

El frontend se conecta a ws://<host>/ws/notificaciones/ y recibe
actualizaciones de contadores sin necesidad de polling.
"""
import json

from channels.generic.websocket import AsyncWebsocketConsumer


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4001)
            return

        self.group_name = f"notif_user_{user.pk}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        # El cliente puede enviar "ping" para mantener la conexión viva
        pass

    async def notification_update(self, event):
        """Recibe mensajes del channel layer y los envía al cliente WebSocket."""
        await self.send(text_data=json.dumps(event["data"]))
