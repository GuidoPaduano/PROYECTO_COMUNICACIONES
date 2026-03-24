from __future__ import annotations

import logging

from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import (
    TokenBlacklistSerializer,
    TokenObtainPairSerializer,
    TokenRefreshSerializer,
    TokenVerifySerializer,
)

logger = logging.getLogger(__name__)


def _cookie_kwargs():
    secure = bool(getattr(settings, "JWT_COOKIE_SECURE", not settings.DEBUG))
    samesite = getattr(settings, "JWT_COOKIE_SAMESITE", "Lax")
    domain = getattr(settings, "JWT_COOKIE_DOMAIN", None) or None
    path = getattr(settings, "JWT_COOKIE_PATH", "/")
    return {
        "httponly": True,
        "secure": secure,
        "samesite": samesite,
        "domain": domain,
        "path": path,
    }


def _set_token_cookies(response: Response, *, access: str | None = None, refresh: str | None = None) -> Response:
    kwargs = _cookie_kwargs()
    if access:
        response.set_cookie(
            getattr(settings, "JWT_ACCESS_COOKIE_NAME", "access_token"),
            access,
            max_age=int(getattr(settings, "JWT_ACCESS_COOKIE_AGE", 3600)),
            **kwargs,
        )
    if refresh:
        response.set_cookie(
            getattr(settings, "JWT_REFRESH_COOKIE_NAME", "refresh_token"),
            refresh,
            max_age=int(getattr(settings, "JWT_REFRESH_COOKIE_AGE", 7 * 24 * 3600)),
            **kwargs,
        )
    return response


def clear_auth_cookies(response: Response) -> Response:
    kwargs = {
        "domain": getattr(settings, "JWT_COOKIE_DOMAIN", None) or None,
        "path": getattr(settings, "JWT_COOKIE_PATH", "/"),
        "samesite": getattr(settings, "JWT_COOKIE_SAMESITE", "Lax"),
    }
    response.delete_cookie(getattr(settings, "JWT_ACCESS_COOKIE_NAME", "access_token"), **kwargs)
    response.delete_cookie(getattr(settings, "JWT_REFRESH_COOKIE_NAME", "refresh_token"), **kwargs)
    return response


def _refresh_from_request(request) -> str:
    payload = getattr(request, "data", {}) or {}
    refresh = (payload.get("refresh") or "").strip()
    if refresh:
        return refresh
    return (request.COOKIES.get(getattr(settings, "JWT_REFRESH_COOKIE_NAME", "refresh_token")) or "").strip()


@method_decorator(csrf_exempt, name="dispatch")
class SafeTokenObtainPairView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        try:
            serializer = TokenObtainPairSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            tokens = serializer.validated_data
            response = Response({"detail": "ok"}, status=status.HTTP_200_OK)
            return _set_token_cookies(
                response,
                access=tokens.get("access"),
                refresh=tokens.get("refresh"),
            )
        except (InvalidToken, TokenError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
        except (AuthenticationFailed, ValidationError) as exc:
            detail = getattr(exc, "detail", None) or "Credenciales inválidas"
            return Response({"detail": detail}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception:
            logger.exception("Error en /api/token/")
            return Response({"detail": "Error interno al generar el token"}, status=500)


@method_decorator(csrf_exempt, name="dispatch")
class SafeTokenRefreshView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        try:
            refresh = _refresh_from_request(request)
            serializer = TokenRefreshSerializer(data={"refresh": refresh})
            serializer.is_valid(raise_exception=True)
            tokens = serializer.validated_data
            response = Response({"detail": "ok"}, status=status.HTTP_200_OK)
            return _set_token_cookies(
                response,
                access=tokens.get("access"),
                refresh=tokens.get("refresh"),
            )
        except (InvalidToken, TokenError) as exc:
            response = Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
            return clear_auth_cookies(response)
        except Exception:
            logger.exception("Error en /api/token/refresh/")
            response = Response({"detail": "Error interno al refrescar el token"}, status=500)
            return clear_auth_cookies(response)


@method_decorator(csrf_exempt, name="dispatch")
class SafeTokenVerifyView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        try:
            token = (
                (getattr(request, "data", {}) or {}).get("token")
                or request.COOKIES.get(getattr(settings, "JWT_ACCESS_COOKIE_NAME", "access_token"))
                or ""
            )
            serializer = TokenVerifySerializer(data={"token": token})
            serializer.is_valid(raise_exception=True)
            return Response({"detail": "ok"}, status=status.HTTP_200_OK)
        except (InvalidToken, TokenError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception:
            logger.exception("Error en /api/token/verify/")
            return Response({"detail": "Error interno al verificar el token"}, status=500)


@method_decorator(csrf_exempt, name="dispatch")
class SafeTokenBlacklistView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        try:
            refresh = _refresh_from_request(request)
            serializer = TokenBlacklistSerializer(data={"refresh": refresh})
            serializer.is_valid(raise_exception=True)
            serializer.save()
            response = Response({"detail": "ok"}, status=status.HTTP_200_OK)
            return clear_auth_cookies(response)
        except (InvalidToken, TokenError) as exc:
            response = Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
            return clear_auth_cookies(response)
        except Exception:
            logger.exception("Error en /api/token/blacklist/")
            response = Response({"detail": "Error interno al cerrar sesiÃ³n"}, status=500)
            return clear_auth_cookies(response)
