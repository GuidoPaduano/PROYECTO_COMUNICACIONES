from __future__ import annotations

from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser


@database_sync_to_async
def _get_user_from_jwt(token_str: str):
    try:
        from rest_framework_simplejwt.tokens import AccessToken
        from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

        token = AccessToken(token_str)
        user_id = token.get("user_id")
        if user_id is None:
            return AnonymousUser()
        User = get_user_model()
        return User.objects.select_related().get(pk=user_id, is_active=True)
    except Exception:
        return AnonymousUser()


def _cookie_value(cookie_header: str, name: str) -> str | None:
    for part in cookie_header.split(";"):
        part = part.strip()
        if part.startswith(f"{name}="):
            return part[len(name) + 1:]
    return None


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        from django.conf import settings

        cookie_name = getattr(settings, "JWT_ACCESS_COOKIE_NAME", "access_token")
        headers = dict(scope.get("headers", []))
        cookie_header = headers.get(b"cookie", b"").decode("utf-8", errors="ignore")
        token_str = _cookie_value(cookie_header, cookie_name)

        scope["user"] = (
            await _get_user_from_jwt(token_str) if token_str else AnonymousUser()
        )

        return await super().__call__(scope, receive, send)
