from django.core.cache import cache
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

try:
    from .models import Alumno, resolve_school_course_for_value  # type: ignore
except Exception:
    Alumno = None
    resolve_school_course_for_value = None

from .contexto import resolve_alumno_for_user
from .schools import resolve_school_for_user


MI_CURSO_CACHE_TTL = 120


def _mi_curso_cache_key(user_id, school_id) -> str:
    return f"mi_curso:user:{user_id or 'x'}:school:{school_id or 'none'}"


def _payload_for_alumno(alumno, *, school=None):
    school_course = getattr(alumno, "school_course", None)
    if school_course is None and resolve_school_course_for_value is not None:
        try:
            school_course = resolve_school_course_for_value(
                school=school,
                curso=getattr(alumno, "curso", None),
            )
        except Exception:
            school_course = None
    return {
        "school_course_id": getattr(school_course, "id", None),
        "school_course_name": (
            getattr(school_course, "name", None)
            or getattr(school_course, "code", None)
            or None
        ),
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def mi_curso(request):
    """
    Devuelve el curso del alumno logueado.

    Respuesta:
      {"school_course_id": 14, "school_course_name": "1A Norte"}
      o valores nulos si no esta linkeado.
    """
    if Alumno is None:
        return Response({"school_course_id": None, "school_course_name": None}, status=status.HTTP_200_OK)

    active_school = resolve_school_for_user(request.user)
    cache_key = _mi_curso_cache_key(getattr(request.user, "id", None), getattr(active_school, "id", None))
    try:
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached, status=status.HTTP_200_OK)
    except Exception:
        pass

    try:
        resolution = resolve_alumno_for_user(request.user, school=active_school)
        if resolution.alumno is not None:
            payload = _payload_for_alumno(resolution.alumno, school=active_school)
            cache.set(cache_key, payload, MI_CURSO_CACHE_TTL)
            return Response(payload, status=status.HTTP_200_OK)
    except Exception:
        pass

    payload = {"school_course_id": None, "school_course_name": None}
    try:
        cache.set(cache_key, payload, MI_CURSO_CACHE_TTL)
    except Exception:
        pass
    return Response(payload, status=status.HTTP_200_OK)
