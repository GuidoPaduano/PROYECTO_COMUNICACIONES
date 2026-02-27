# calificaciones/api_eventos_padres.py
from django.http import JsonResponse, HttpResponseForbidden
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import Alumno, Evento

def _serialize_evento(ev: Evento):
    # Estructura compatible con tu FullCalendar adapter actual
    start = None
    try:
        start = ev.fecha.isoformat()
    except Exception:
        start = str(getattr(ev, "fecha", ""))

    return {
        "id": str(getattr(ev, "id", "")),
        "title": getattr(ev, "titulo", "") or getattr(ev, "title", ""),
        "start": start,
        "extendedProps": {
            "description": getattr(ev, "descripcion", "") or getattr(ev, "description", ""),
            "curso": getattr(ev, "curso", ""),
            "tipo_evento": getattr(ev, "tipo_evento", ""),
        },
    }

def _parse_date(s):
    if not s:
        return None
    d = parse_date(s)
    return d

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
    alumno = get_object_or_404(Alumno, id_alumno=alumno_id)

    # Autorización: padre del alumno o superuser
    if not request.user.is_superuser and alumno.padre_id != request.user.id:
        return HttpResponseForbidden("No tenés permiso.")

    qs = (
        Evento.objects.filter(
            Q(curso=alumno.curso)
            | Q(curso__iexact="ALL")
            | Q(curso__iexact="TODOS")
            | Q(curso="*")
        )
        .order_by("fecha", "id")
    )

    # Rango opcional
    desde = _parse_date(request.GET.get("desde"))
    hasta = _parse_date(request.GET.get("hasta"))
    if desde:
        qs = qs.filter(fecha__gte=desde)
    if hasta:
        qs = qs.filter(fecha__lte=hasta)

    data = [_serialize_evento(e) for e in qs]
    return JsonResponse({"ok": True, "alumno": alumno_id, "curso": alumno.curso, "results": data})

@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def eventos_para_mis_hijos(request):
    """
    Devuelve la unión de eventos de los cursos de TODOS los hijos del padre.
    Filtros opcionales ?desde y ?hasta (YYYY-MM-DD).
    """
    if request.user.is_superuser:
        hijos = Alumno.objects.all()
    else:
        hijos = Alumno.objects.filter(padre=request.user)

    cursos = sorted({h.curso for h in hijos if h.curso})
    qs = (
        Evento.objects.filter(
            Q(curso__in=cursos)
            | Q(curso__iexact="ALL")
            | Q(curso__iexact="TODOS")
            | Q(curso="*")
        )
        .order_by("fecha", "id")
    )

    desde = _parse_date(request.GET.get("desde"))
    hasta = _parse_date(request.GET.get("hasta"))
    if desde:
        qs = qs.filter(fecha__gte=desde)
    if hasta:
        qs = qs.filter(fecha__lte=hasta)

    data = [_serialize_evento(e) for e in qs]
    return JsonResponse({"ok": True, "cursos": cursos, "results": data})
