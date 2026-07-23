import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "boletin.settings")

from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path
from calificaciones.consumers import NotificationConsumer
from boletin.ws_middleware import JWTAuthMiddleware

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddleware(
        URLRouter([
            path("ws/notificaciones/", NotificationConsumer.as_asgi()),
        ])
    ),
})
