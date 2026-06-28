import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "boletin.settings")

from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.urls import path
from calificaciones.consumers import NotificationConsumer

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter([
            path("ws/notificaciones/", NotificationConsumer.as_asgi()),
        ])
    ),
})
