from __future__ import annotations

from django.conf import settings
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


class CookieJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        header = self.get_header(request)
        if header is not None:
            return super().authenticate(request)

        raw_token = request.COOKIES.get(getattr(settings, "JWT_ACCESS_COOKIE_NAME", "access_token"))
        if not raw_token:
            return None

        # Token inválido o expirado → anónimo para no bloquear endpoints AllowAny.
        try:
            validated_token = self.get_validated_token(raw_token)
        except (InvalidToken, TokenError):
            return None

        # CSRF no se verifica explícitamente porque JWT_COOKIE_SAMESITE=Lax ya
        # impide que browsers envíen la cookie en mutaciones cross-site.
        return self.get_user(validated_token), validated_token

    def get_user(self, validated_token):
        from django.db.models import prefetch_related_objects
        user = super().get_user(validated_token)
        if user is not None:
            # Prefetch groups once so get_user_group_names() reads _prefetched_objects_cache
            # instead of firing a second query on every authenticated request.
            prefetch_related_objects([user], "groups")
        return user
