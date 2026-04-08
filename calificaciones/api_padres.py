# calificaciones/api_padres.py
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404
from django.core.cache import cache

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated

from .jwt_auth import CookieJWTAuthentication as JWTAuthentication
from .models import Alumno, Nota
from .schools import get_request_school, scope_queryset_to_school


MIS_HIJOS_CACHE_TTL = 120


def _mis_hijos_cache_key(user_id, school_id, is_superuser: bool) -> str:
    return f"mis_hijos:user:{user_id or 'x'}:school:{school_id or 'none'}:super:{int(bool(is_superuser))}"


def _serialize_alumnos_public(qs):
    """Serializa alumnos para la API publica de padres."""
    out = []
    for alumno in qs:
        school_course = getattr(alumno, "school_course", None)
        out.append(
            {
                "id": getattr(alumno, "id", None),
                "id_alumno": getattr(alumno, "id_alumno", None),
                "nombre": getattr(alumno, "nombre", None),
                # Algunas filas antiguas pueden no tener apellido.
                "apellido": getattr(alumno, "apellido", None),
                "school_course_id": getattr(alumno, "school_course_id", None),
                "school_course_name": getattr(school_course, "name", None)
                or getattr(school_course, "code", None)
                or getattr(alumno, "curso", None),
            }
        )
    return out


def _serialize_notas_public(qs):
    """Serializa notas para la API publica de padres."""
    out = []
    for nota in qs:
        out.append(
            {
                "id": getattr(nota, "id", None),
                "fecha": getattr(nota, "fecha", None),
                "materia": getattr(nota, "materia", None),
                "tipo": getattr(nota, "tipo", None),
                "calificacion": getattr(nota, "calificacion", None),
                "calificacion_display": getattr(nota, "calificacion_display", None),
                "cuatrimestre": getattr(nota, "cuatrimestre", None),
            }
        )
    return out


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mis_hijos(request):
    """
    Devuelve los alumnos vinculados al usuario padre autenticado.
    Compatible con JWT (authFetch) y sesion.
    """
    active_school = get_request_school(request)
    cache_key = _mis_hijos_cache_key(
        getattr(request.user, "id", None),
        getattr(active_school, "id", None),
        getattr(request.user, "is_superuser", False),
    )
    try:
        cached = cache.get(cache_key)
        if cached is not None:
            return JsonResponse(cached)
    except Exception:
        pass

    qs = scope_queryset_to_school(
        Alumno.objects.select_related("school_course"),
        active_school,
    )
    if not request.user.is_superuser:
        qs = qs.filter(padre=request.user)

    # Orden consistente; degradamos si algun campo no existe.
    try:
        qs = qs.order_by("apellido", "nombre", "id_alumno")
    except Exception:
        try:
            qs = qs.order_by("nombre", "id_alumno")
        except Exception:
            qs = qs.order_by("id_alumno")

    # Serializacion explicita para mantener el contrato publico.
    data = _serialize_alumnos_public(qs)
    payload = {"results": data}
    try:
        cache.set(cache_key, payload, MIS_HIJOS_CACHE_TTL)
    except Exception:
        pass
    return JsonResponse(payload)


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def notas_de_hijo(request, alumno_id):
    """
    Devuelve las notas del alumno indicado si pertenece al usuario padre.
    Filtros por querystring:
      - materia: nombre exacto (Nota.materia)
      - cuatrimestre: valor exacto (p.ej. "1", "2", "Anual")
    Devuelve ademas catalogos: materias y cuatrimestres disponibles para ese alumno.
    """
    active_school = get_request_school(request)
    alumnos_qs = scope_queryset_to_school(Alumno.objects.all(), active_school)
    alumno = get_object_or_404(alumnos_qs, id_alumno=alumno_id)

    # Autorizacion: padre del alumno o superuser.
    if not request.user.is_superuser and alumno.padre_id != request.user.id:
        return HttpResponseForbidden("No tenes permiso para ver las notas de este alumno.")

    # Filtros desde querystring.
    materia_q = (request.GET.get("materia") or "").strip()
    cuatri_q = (request.GET.get("cuatrimestre") or "").strip()

    qs = scope_queryset_to_school(Nota.objects.filter(alumno=alumno), active_school)
    if materia_q:
        qs = qs.filter(materia=materia_q)
    if cuatri_q:
        qs = qs.filter(cuatrimestre=cuatri_q)
    qs = qs.order_by("-fecha", "-id")

    # Serializacion explicita para mantener el contrato publico.
    notas_data = _serialize_notas_public(qs)

    # Catalogos derivados sobre todas las notas del alumno, sin filtros.
    all_qs = scope_queryset_to_school(Nota.objects.filter(alumno=alumno), active_school)
    materias = sorted(
        {getattr(nota, "materia", None) for nota in all_qs if getattr(nota, "materia", None)}
    )
    cuatrimestres = sorted(
        {
            getattr(nota, "cuatrimestre", None)
            for nota in all_qs
            if getattr(nota, "cuatrimestre", None)
        }
    )

    school_course = getattr(alumno, "school_course", None)
    alumno_payload = {
        "id": getattr(alumno, "id", None),
        "id_alumno": getattr(alumno, "id_alumno", None),
        "nombre": getattr(alumno, "nombre", None),
        "apellido": getattr(alumno, "apellido", None),  # Puede ser None en datos historicos.
        "school_course_id": getattr(alumno, "school_course_id", None),
        "school_course_name": getattr(school_course, "name", None)
        or getattr(school_course, "code", None)
        or getattr(alumno, "curso", None),
    }

    return JsonResponse(
        {
            "alumno": alumno_payload,
            "filters": {"materia": materia_q, "cuatrimestre": cuatri_q},
            "materias": materias,
            "cuatrimestres": cuatrimestres,
            "results": notas_data,
        }
    )
