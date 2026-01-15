# calificaciones/api_notas.py
from __future__ import annotations

from typing import Optional

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import Alumno, Nota
from .serializers import NotaPublicSerializer
from .contexto import resolve_alumno_for_user

try:
    # Si existe el modelo real de preceptor → cursos
    from .models_preceptores import PreceptorCurso  # type: ignore
except Exception:
    PreceptorCurso = None


# =========================================================
#  Auth de sesión sin CSRF (para SPA en desarrollo)
# =========================================================
class CsrfExemptSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request):
        return  # no-op


def _has_model_field(model, name: str) -> bool:
    try:
        model._meta.get_field(name)
        return True
    except Exception:
        return False


def _preceptor_can_access_alumno(user, alumno: Alumno) -> bool:
    """
    Permite acceso a un preceptor SOLO si el curso del alumno está asignado a ese preceptor.

    - Requiere que exista el modelo PreceptorCurso (si no existe, se deniega para evitar abrir acceso).
    - Intenta varias convenciones de nombre de FK al user para ser robusto.
    """
    if PreceptorCurso is None:
        return False

    # Si Alumno no tuviera "curso", no podemos chequear nada => denegamos.
    curso_alumno = getattr(alumno, "curso", None)
    if not curso_alumno:
        return False

    # Intentos comunes de nombre de campo en PreceptorCurso
    possible_user_fields = ["preceptor", "usuario", "user", "remitente", "docente"]
    possible_curso_fields = ["curso", "curso_id", "curso_codigo", "curso_nombre"]

    # Primero: intentamos el caso más probable: preceptor + curso
    try:
        return PreceptorCurso.objects.filter(preceptor=user, curso=curso_alumno).exists()
    except Exception:
        pass

    # Segundo: intentamos combinaciones posibles de nombres de campo
    for uf in possible_user_fields:
        for cf in possible_curso_fields:
            try:
                kwargs = {uf: user, cf: curso_alumno}
                if PreceptorCurso.objects.filter(**kwargs).exists():
                    return True
            except Exception:
                continue

    return False


def _authorize_alumno(request, alumno: Alumno) -> bool:
    """
    Autorización básica:
    - superuser
    - Profesores
    - Preceptores (SOLO si el alumno es de un curso asignado)
    - Padre del alumno
    - El propio alumno vinculado (Alumno.usuario)
    """
    user = request.user

    if getattr(user, "is_superuser", False):
        return True

    if user.groups.filter(name="Profesores").exists():
        return True

    # Preceptores con restricción por curso
    if user.groups.filter(name="Preceptores").exists():
        return _preceptor_can_access_alumno(user, alumno)

    if getattr(alumno, "padre_id", None) == user.id:
        return True

    # Alumno propio: 1) vínculo explícito Alumno.usuario (si existe)
    #               2) fallback robusto (username==legajo, etc.)
    if getattr(alumno, "usuario_id", None) == user.id:
        return True

    try:
        r = resolve_alumno_for_user(user)
        if r.alumno and r.alumno.id == alumno.id:
            return True
    except Exception:
        pass

    return False


def _notas_response(alumno: Alumno):
    qs = Nota.objects.filter(alumno=alumno)

    # Orden consistente: por cuatrimestre y, si existe, por fecha
    if _has_model_field(Nota, "fecha"):
        qs = qs.order_by("cuatrimestre", "fecha", "materia")
    else:
        qs = qs.order_by("cuatrimestre", "materia")

    data = NotaPublicSerializer(qs, many=True).data
    return Response(
        {
            "alumno": {"id": alumno.id, "id_alumno": alumno.id_alumno, "nombre": alumno.nombre},
            "notas": data,
        }
    )


def _get_alumno_from_query_params(request) -> Optional[Alumno]:
    """
    Soporta estas variantes:
    - ?alumno=<pk>              (compat con tu frontend/logs)
    - ?alumno=<id_alumno>       (si no es dígito, se toma como legajo/código)
    - ?alumno_id=<pk>
    - ?id_alumno=<código>

    Devuelve Alumno o None si faltan params.
    Lanza DoesNotExist si no existe (lo manejamos afuera).
    """
    alumno_param = (request.GET.get("alumno") or "").strip()
    alumno_id = (request.GET.get("alumno_id") or "").strip()
    id_alumno = (request.GET.get("id_alumno") or "").strip()

    # Prioridad: alumno (nuevo compat)
    if alumno_param:
        if alumno_param.isdigit():
            return Alumno.objects.get(pk=int(alumno_param))
        # si no es dígito, lo tratamos como legajo/código
        return Alumno.objects.get(id_alumno=str(alumno_param))

    # Legacy: id_alumno
    if id_alumno:
        return Alumno.objects.get(id_alumno=str(id_alumno))

    # Legacy: alumno_id
    if alumno_id:
        if alumno_id.isdigit():
            return Alumno.objects.get(pk=int(alumno_id))
        # si vino algo raro, intentamos como id_alumno por las dudas
        return Alumno.objects.get(id_alumno=str(alumno_id))

    return None


@api_view(["GET"])
@authentication_classes([CsrfExemptSessionAuthentication, JWTAuthentication])
@permission_classes([IsAuthenticated])
def notas_listar(request):
    """
    ✅ Compat:
    GET /api/notas/?id_alumno=00001
    GET /api/notas/?alumno_id=<pk>
    ✅ NUEVO (por tus logs/frontend):
    GET /api/notas/?alumno=<pk>
    GET /api/notas/?alumno=<id_alumno>
    """
    try:
        alumno = _get_alumno_from_query_params(request)
        if alumno is None:
            return Response(
                {"detail": "Falta alumno, alumno_id o id_alumno"},
                status=400,
            )
    except Alumno.DoesNotExist:
        return Response({"detail": "Alumno no encontrado"}, status=404)

    if not _authorize_alumno(request, alumno):
        return Response({"detail": "No autorizado"}, status=403)

    return _notas_response(alumno)


@api_view(["GET"])
@authentication_classes([CsrfExemptSessionAuthentication, JWTAuthentication])
@permission_classes([IsAuthenticated])
def notas_por_codigo(request, id_alumno: str):
    """
    ✅ Compat legacy:
    GET /api/notas/alumno_codigo/<id_alumno>/
    """
    try:
        alumno = Alumno.objects.get(id_alumno=str(id_alumno))
    except Alumno.DoesNotExist:
        return Response({"detail": "Alumno no encontrado"}, status=404)

    if not _authorize_alumno(request, alumno):
        return Response({"detail": "No autorizado"}, status=403)

    return _notas_response(alumno)
