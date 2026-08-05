from __future__ import annotations

from django.conf import settings
from django.middleware.csrf import CsrfViewMiddleware
from rest_framework import exceptions
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


class _CSRFCheck(CsrfViewMiddleware):
    """Subclase que devuelve el motivo del rechazo en vez de un HttpResponse."""
    def _reject(self, request, reason):
        return reason


class CookieJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        header = self.get_header(request)
        if header is not None:
            # Autenticación por header Authorization: no requiere CSRF.
            return super().authenticate(request)

        raw_token = request.COOKIES.get(getattr(settings, "JWT_ACCESS_COOKIE_NAME", "access_token"))
        if not raw_token:
            return None

        # Token en cookie inválido o expirado → tratar como anónimo para no
        # bloquear endpoints públicos (AllowAny) con cookies obsoletas.
        try:
            validated_token = self.get_validated_token(raw_token)
        except (InvalidToken, TokenError):
            return None

        # Cookie válida: enforce CSRF igual que SessionAuthentication de DRF.
        self._enforce_csrf(request)

        return self.get_user(validated_token), validated_token

    def _enforce_csrf(self, request):
        check = _CSRFCheck(get_response=lambda r: None)
        check.process_request(request)
        reason = check.process_view(request, None, (), {})
        if reason:
            raise exceptions.PermissionDenied(f"CSRF verificación fallida: {reason}")

    def get_user(self, validated_token):
        from django.db.models import prefetch_related_objects
        user = super().get_user(validated_token)
        if user is not None:
            # Prefetch groups once so get_user_group_names() reads _prefetched_objects_cache
            # instead of firing a second query on every authenticated request.
            prefetch_related_objects([user], "groups")
        return user
