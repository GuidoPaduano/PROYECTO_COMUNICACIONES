from __future__ import annotations

import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.translation import gettext as _

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes, parser_classes, throttle_classes
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from .resend_email import send_resend_email


def _frontend_base_url(request) -> str:
    base = (getattr(settings, "FRONTEND_BASE_URL", "") or "").strip()
    if base:
        return base
    env_base = (os.environ.get("FRONTEND_BASE_URL", "") or "").strip()
    if env_base:
        return env_base
    return ""


def _reset_path() -> str:
    path = (getattr(settings, "PASSWORD_RESET_PATH", "") or "").strip()
    if path:
        return path
    env_path = (os.environ.get("PASSWORD_RESET_PATH", "") or "").strip()
    if env_path:
        return env_path
    return "/reset-password"

def _blacklist_all_tokens(user) -> None:
    try:
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken

        tokens = OutstandingToken.objects.filter(user=user)
        for tok in tokens:
            BlacklistedToken.objects.get_or_create(token=tok)
    except Exception:
        pass


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@parser_classes([JSONParser, FormParser, MultiPartParser])
@throttle_classes([AnonRateThrottle, UserRateThrottle])
def password_reset_request(request):
    payload = request.data or {}
    email = (payload.get("email") or payload.get("correo") or "").strip().lower()

    # Respuesta genérica para no exponer si el correo existe.
    generic_response = {"detail": _("Si el correo existe, te enviaremos un link para restablecer tu contraseña.")}

    if not email:
        return Response({"detail": _("Ingresá un correo válido.")}, status=status.HTTP_400_BAD_REQUEST)

    User = get_user_model()
    user = User.objects.filter(email__iexact=email, is_active=True).order_by("id").first()
    if not user:
        return Response(generic_response, status=status.HTTP_200_OK)

    uid = urlsafe_base64_encode(str(user.pk).encode("utf-8"))
    token = default_token_generator.make_token(user)

    base = _frontend_base_url(request).rstrip("/")
    if not base:
        return Response({"detail": _("Configuración de frontend no definida.")}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    path = _reset_path().strip()
    if not path.startswith("/"):
        path = f"/{path}"
    reset_url = f"{base}{path}?uid={uid}&token={token}"

    subject = "Restablecer contraseña"
    text = (
        "Solicitaste restablecer tu contraseña.\n\n"
        f"Usá este link para continuar:\n{reset_url}\n\n"
        "Si no fuiste vos, podés ignorar este correo."
    )
    html = (
        "<p>Solicitaste restablecer tu contraseña.</p>"
        f"<p><a href=\"{reset_url}\">Hacé clic aquí para continuar</a></p>"
        "<p>Si no fuiste vos, podés ignorar este correo.</p>"
    )

    send_resend_email(to_email=email, subject=subject, text=text, html=html)

    return Response(generic_response, status=status.HTTP_200_OK)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@parser_classes([JSONParser, FormParser, MultiPartParser])
@throttle_classes([AnonRateThrottle, UserRateThrottle])
def password_reset_confirm(request):
    payload = request.data or {}
    uid = (payload.get("uid") or "").strip()
    token = (payload.get("token") or "").strip()
    password = (payload.get("password") or payload.get("new_password") or "").strip()

    if not uid or not token or not password:
        return Response({"detail": _("Datos incompletos.")}, status=status.HTTP_400_BAD_REQUEST)

    try:
        uid_decoded = force_str(urlsafe_base64_decode(uid))
        User = get_user_model()
        user = User.objects.get(pk=uid_decoded)
    except Exception:
        return Response({"detail": _("Link inválido o expirado.")}, status=status.HTTP_400_BAD_REQUEST)

    if not default_token_generator.check_token(user, token):
        return Response({"detail": _("Link inválido o expirado.")}, status=status.HTTP_400_BAD_REQUEST)

    user.set_password(password)
    user.save(update_fields=["password"])
    _blacklist_all_tokens(user)

    return Response({"detail": _("Contraseña actualizada.")}, status=status.HTTP_200_OK)
