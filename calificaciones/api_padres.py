# calificaciones/api_padres.py
from django.shortcuts import get_object_or_404
from django.http import JsonResponse, HttpResponseForbidden

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import Alumno, Nota

# --- Serializers: intentamos usar los tuyos; si no existen, caemos a fallbacks seguros ---
AlumnoSerializer = None
try:
    # Tu serializer habitual (si existe)
    from .serializers import AlumnoSerializer as _AlumnoSerializer
    AlumnoSerializer = _AlumnoSerializer
except Exception:
    try:
        from .serializers import AlumnoFullSerializer as _AlumnoSerializer
        AlumnoSerializer = _AlumnoSerializer
    except Exception:
        try:
            from .serializers import AlumnoPublicSerializer as _AlumnoSerializer
            AlumnoSerializer = _AlumnoSerializer
        except Exception:
            AlumnoSerializer = None  # usaremos un fallback manual

NotaPublicSerializer = None
try:
    from .serializers import NotaPublicSerializer as _NotaPublicSerializer
    NotaPublicSerializer = _NotaPublicSerializer
except Exception:
    NotaPublicSerializer = None  # usaremos un fallback manual si fuera necesario


def _json_error(msg, status=400):
    return JsonResponse({"ok": False, "error": msg}, status=status)


def _serialize_alumnos_fallback(qs):
    """Serializador mínimo si no hay serializer DRF disponible."""
    out = []
    for a in qs:
        out.append({
            "id_alumno": getattr(a, "id_alumno", None),
            "nombre": getattr(a, "nombre", None),
            # algunos proyectos tuyos no tenían 'apellido'; por eso usamos getattr
            "apellido": getattr(a, "apellido", None),
            "curso": getattr(a, "curso", None),
        })
    return out


def _serialize_notas_fallback(qs):
    """Serializador mínimo para notas si no está NotaPublicSerializer."""
    out = []
    for n in qs:
        out.append({
            "id": getattr(n, "id", None),
            "fecha": getattr(n, "fecha", None),
            "materia": getattr(n, "materia", None),
            "tipo": getattr(n, "tipo", None),
            "calificacion": getattr(n, "calificacion", None),
            "calificacion_display": getattr(n, "calificacion_display", None),
            "cuatrimestre": getattr(n, "cuatrimestre", None),
        })
    return out


@api_view(["GET"])
@authentication_classes([JWTAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
def mis_hijos(request):
    """
    Devuelve los alumnos vinculados al usuario padre autenticado.
    Compatible con JWT (authFetch) y sesión.
    """
    qs = Alumno.objects.all()
    if not request.user.is_superuser:
        qs = qs.filter(padre=request.user)

    # Orden consistente; degradamos si algún campo no existe
    try:
        qs = qs.order_by("apellido", "nombre", "id_alumno")
    except Exception:
        try:
            qs = qs.order_by("nombre", "id_alumno")
        except Exception:
            qs = qs.order_by("id_alumno")

    # Serialización robusta
    try:
        data = AlumnoSerializer(qs, many=True).data if AlumnoSerializer else _serialize_alumnos_fallback(qs)
    except Exception:
        data = _serialize_alumnos_fallback(qs)

    return JsonResponse({"ok": True, "results": data})


@api_view(["GET"])
@authentication_classes([JWTAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
def notas_de_hijo(request, alumno_id):
    """
    Devuelve las notas del alumno indicado si pertenece al usuario padre.
    Filtros por querystring:
      - materia: nombre exacto (Nota.materia)
      - cuatrimestre: valor exacto (p.ej. "1", "2", "Anual")
    Devuelve además catálogos: materias y cuatrimestres disponibles para ese alumno.
    """
    alumno = get_object_or_404(Alumno, id_alumno=alumno_id)

    # Autorización: padre del alumno o superuser
    if not request.user.is_superuser and alumno.padre_id != request.user.id:
        return HttpResponseForbidden("No tenés permiso para ver las notas de este alumno.")

    # --- Filtros desde querystring ---
    materia_q = (request.GET.get("materia") or "").strip()
    cuatri_q = (request.GET.get("cuatrimestre") or "").strip()

    qs = Nota.objects.filter(alumno=alumno)
    if materia_q:
        qs = qs.filter(materia=materia_q)
    if cuatri_q:
        qs = qs.filter(cuatrimestre=cuatri_q)
    qs = qs.order_by("-fecha", "-id")

    # Serialización robusta
    try:
        notas_data = NotaPublicSerializer(qs, many=True).data if NotaPublicSerializer else _serialize_notas_fallback(qs)
    except Exception:
        notas_data = _serialize_notas_fallback(qs)

    # Catálogos derivados (sobre todas las notas del alumno, sin filtros)
    all_qs = Nota.objects.filter(alumno=alumno)
    materias = sorted({getattr(n, "materia", None) for n in all_qs if getattr(n, "materia", None)})
    cuatrimestres = sorted({getattr(n, "cuatrimestre", None) for n in all_qs if getattr(n, "cuatrimestre", None)})

    alumno_payload = {
        "id_alumno": getattr(alumno, "id_alumno", None),
        "nombre": getattr(alumno, "nombre", None),
        "apellido": getattr(alumno, "apellido", None),  # puede ser None si el modelo no lo tiene
        "curso": getattr(alumno, "curso", None),
    }

    return JsonResponse({
        "ok": True,
        "alumno": alumno_payload,
        "filters": {"materia": materia_q, "cuatrimestre": cuatri_q},
        "materias": materias,
        "cuatrimestres": cuatrimestres,
        "results": notas_data,
    })
