# calificaciones/api_eventos_padres.py
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from .jwt_auth import CookieJWTAuthentication as JWTAuthentication

from .course_access import build_course_membership_q_for_refs, build_course_ref
from .models import Alumno, Evento
from .schools import get_request_school, scope_queryset_to_school
from .utils_cursos import get_course_label


def _padre_hijos_qs(*, user, school=None):
    qs = Alumno.objects.select_related("school", "school_course")
    qs = scope_queryset_to_school(qs, school)
    if getattr(user, "is_superuser", False):
        return qs
    return qs.filter(padre=user)


def _eventos_qs(*, school=None):
    qs = Evento.objects.select_related("school", "school_course")
    return scope_queryset_to_school(qs, school)


def _serialize_evento(ev: Evento):
    # Estructura compatible con el adapter actual de FullCalendar.
    start = None
    try:
        start = ev.fecha.isoformat()
    except Exception:
        start = str(getattr(ev, "fecha", ""))
    school_course = getattr(ev, "school_course", None)
    curso_nombre = (
        getattr(school_course, "name", None)
        or getattr(school_course, "code", None)
        or get_course_label(getattr(ev, "curso", ""), school=getattr(ev, "school", None))
    )

    return {
        "id": str(getattr(ev, "id", "")),
        "school_course_id": getattr(ev, "school_course_id", None),
        "school_course_name": curso_nombre,
        "title": getattr(ev, "titulo", "") or getattr(ev, "title", ""),
        "start": start,
        "extendedProps": {
            "description": getattr(ev, "descripcion", "") or getattr(ev, "description", ""),
            "school_course_name": curso_nombre,
            "school_course_id": getattr(ev, "school_course_id", None),
            "tipo_evento": getattr(ev, "tipo_evento", ""),
        },
    }

def _parse_date(s):
    if not s:
        return None
    return parse_date(s)

@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def eventos_para_hijo(request, alumno_id: str):
    """
    Devuelve SOLO eventos del curso del hijo indicado (si el hijo pertenece al padre).
    Filtros opcionales por rango:
      ?desde=YYYY-MM-DD
      ?hasta=YYYY-MM-DD
    """
    active_school = get_request_school(request)
    alumno = get_object_or_404(
        scope_queryset_to_school(
            Alumno.objects.select_related("school", "school_course"),
            active_school,
        ),
        id_alumno=alumno_id,
    )

    # Autorización: padre del alumno o superuser
    if not request.user.is_superuser and alumno.padre_id != request.user.id:
        return HttpResponseForbidden("No tenés permiso.")

    course_q = build_course_membership_q_for_refs(
        [build_course_ref(obj=alumno)],
        school_course_field="school_course",
        code_field="curso",
        include_all_markers=True,
    )
    if course_q is None:
        qs = Evento.objects.none()
    else:
        qs = _eventos_qs(school=active_school).filter(course_q).order_by("fecha", "id")

    # Rango opcional
    desde = _parse_date(request.GET.get("desde"))
    hasta = _parse_date(request.GET.get("hasta"))
    if desde:
        qs = qs.filter(fecha__gte=desde)
    if hasta:
        qs = qs.filter(fecha__lte=hasta)

    data = [_serialize_evento(e) for e in qs]
    alumno_school_course = getattr(alumno, "school_course", None)
    alumno_course_name = getattr(alumno_school_course, "name", None) or get_course_label(alumno.curso, school=getattr(alumno, "school", None))
    return JsonResponse(
        {
            "alumno": alumno_id,
            "school_course_id": getattr(alumno, "school_course_id", None),
            "school_course_name": alumno_course_name,
            "results": data,
        }
    )

@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def eventos_para_mis_hijos(request):
    """
    Devuelve la unión de eventos de los cursos de TODOS los hijos del padre.
    Filtros opcionales ?desde y ?hasta (YYYY-MM-DD).
    """
    active_school = get_request_school(request)
    hijos = list(_padre_hijos_qs(user=request.user, school=active_school))

    course_refs = [build_course_ref(obj=h) for h in hijos]
    course_q = build_course_membership_q_for_refs(
        course_refs,
        school_course_field="school_course",
        code_field="curso",
        include_all_markers=True,
    )
    if course_q is None:
        qs = Evento.objects.none()
    else:
        qs = _eventos_qs(school=active_school).filter(course_q).order_by("fecha", "id")

    desde = _parse_date(request.GET.get("desde"))
    hasta = _parse_date(request.GET.get("hasta"))
    if desde:
        qs = qs.filter(fecha__gte=desde)
    if hasta:
        qs = qs.filter(fecha__lte=hasta)

    data = [_serialize_evento(e) for e in qs]
    return JsonResponse({"results": data})
