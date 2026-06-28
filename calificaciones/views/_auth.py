# calificaciones/views/_auth.py
# Autenticación: mi_perfil, auth_logout, auth_change_password, mensajes_unread_count

from django.contrib.auth import get_user_model
from django.contrib.auth import logout as dj_logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status
from rest_framework.decorators import (
    api_view, authentication_classes, permission_classes,
    parser_classes, throttle_classes,
)
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from ..auth_api import clear_auth_cookies
from ..jwt_auth import CookieJWTAuthentication as JWTAuthentication
from ..schools import (
    get_available_school_dicts_for_user,
    get_request_school,
    school_to_dict,
)
from ..contexto import resolve_alumno_for_user
from ._acceso import (
    _alumno_to_dict,
    _effective_groups,
    _mensajes_inbox_qs,
    _mensajes_unread_count_from_qs,
    _profile_assigned_school_courses,
    _rol_principal,
)


# =========================================================
#  Endpoint JSON minimal legado
# =========================================================
@login_required
def mi_perfil(request):
    """
    Versión minimal del perfil del usuario autenticado.
    """
    user = request.user
    viewer_groups = set(_effective_groups(request))
    active_school = get_request_school(request)
    groups = _effective_groups(request)

    # Alumno propio (resolucion tolerante)
    r = resolve_alumno_for_user(user, school=active_school)
    alumno_vinculado = r.alumno
    assigned_school_courses = _profile_assigned_school_courses(
        user=user,
        groups=groups,
        school=active_school,
    )

    data = {
        "username": user.username,
        "email": user.email,
        "groups": groups,
        "rol": _rol_principal(user),
        "is_superuser": user.is_superuser,
        "school": school_to_dict(active_school),
        "available_schools": get_available_school_dicts_for_user(user, active_school=active_school),
        "assigned_school_courses": assigned_school_courses,
    }

    if alumno_vinculado:
        data["alumno"] = _alumno_to_dict(alumno_vinculado)

    return JsonResponse(data)


# =========================================================
#  Logout de sesión (complementa blacklist de JWT)
# =========================================================
@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def auth_logout(request):
    """
    Cierra la sesión de Django si la hubiera (cookie sessionid) y limpia cookies.
    Para JWT, complementamos con /api/token/blacklist/ desde el front.
    """
    try:
        if request.user.is_authenticated:
            dj_logout(request)
    except Exception:
        pass
    resp = HttpResponse(status=204)
    # Limpieza defensiva de cookies típicas
    resp.delete_cookie("sessionid")
    resp.delete_cookie("csrftoken")
    return clear_auth_cookies(resp)


# =========================================================
#  Cambiar contraseña (autenticado)
# =========================================================
@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
@throttle_classes([UserRateThrottle])
def auth_change_password(request):
    user = request.user
    data = request.data or {}

    current = (data.get("current_password") or data.get("password_actual") or "").strip()
    new = (data.get("new_password") or data.get("password_nueva") or "").strip()

    if not current or not new:
        return Response({"detail": "Completá la contraseña actual y la nueva."}, status=400)

    if not user.check_password(current):
        return Response({"detail": "La contraseña actual no coincide."}, status=400)

    try:
        validate_password(new, user=user)
    except ValidationError as exc:
        return Response({"detail": list(exc.messages)}, status=400)

    user.set_password(new)
    user.save(update_fields=["password"])

    # Revocar refresh tokens existentes si blacklist está habilitado
    try:
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
        tokens = OutstandingToken.objects.filter(user=user)
        for tok in tokens:
            BlacklistedToken.objects.get_or_create(token=tok)
    except Exception:
        pass

    # Mantener la sesión de Django si estuviera usando cookies
    try:
        update_session_auth_hash(request, user)
    except Exception:
        pass

    return Response({"detail": "Contraseña actualizada."})


# =========================================================
#  ✅ NUEVO: contador de no leídos para el badge de la topbar
# =========================================================
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mensajes_unread_count(request):
    user = request.user
    inbox_qs = _mensajes_inbox_qs(user, school=get_request_school(request))
    count = _mensajes_unread_count_from_qs(inbox_qs)
    return Response({"count": count})
