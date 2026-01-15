from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
import logging

logger = logging.getLogger(__name__)

@method_decorator(csrf_exempt, name="dispatch")
class SafeTokenObtainPairView(TokenObtainPairView):
    """/api/token/ — maneja errores y evita CSRF 403 en SPA"""
    def post(self, request, *args, **kwargs):
        try:
            return super().post(request, *args, **kwargs)
        except (InvalidToken, TokenError) as e:
            return Response({"detail": str(e)}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            logger.exception("Error en /api/token/")
            return Response({"detail": "Error interno al generar el token"}, status=500)

@method_decorator(csrf_exempt, name="dispatch")
class SafeTokenRefreshView(TokenRefreshView):
    """/api/token/refresh/ — idem"""
    def post(self, request, *args, **kwargs):
        try:
            return super().post(request, *args, **kwargs)
        except (InvalidToken, TokenError) as e:
            return Response({"detail": str(e)}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            logger.exception("Error en /api/token/refresh/")
            return Response({"detail": "Error interno al refrescar el token"}, status=500)

# Verify no necesita override, pero lo dejo listo por si querés agregar csrf_exempt:
@method_decorator(csrf_exempt, name="dispatch")
class SafeTokenVerifyView(TokenVerifyView):
    pass
