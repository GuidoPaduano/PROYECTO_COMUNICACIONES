# calificaciones/views/_alumnos.py
# API Detalle de Alumno y Notas de un alumno

from django.views.decorators.csrf import csrf_exempt

from rest_framework.decorators import (
    api_view, authentication_classes, permission_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..models_preceptores import SchoolAdmin
from ..contexto import resolve_alumno_for_user
from ..jwt_auth import CookieJWTAuthentication as JWTAuthentication
from ..models import Alumno, Nota
from ..schools import (
    get_request_school,
    scope_queryset_to_school,
)
from ..serializers import AlumnoFullSerializer, NotaPublicSerializer
from ._acceso import (
    _effective_groups,
    _has_role,
    _preceptor_can_access_alumno,
    _profesor_can_access_alumno,
)
from ._cursos import _resolve_alumno_by_pk_or_legajo


# =========================================================
#  API Detalle de Alumno
# =========================================================
@csrf_exempt
@api_view(["GET", "PATCH"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def alumno_detalle(request, alumno_id):
    """
    GET /api/alumnos/<alumno_id>/

    Prioridad de resolución:
      1) Si es numérico, buscar por PK (id interno, usado por los links del front).
      2) Si no existe o no es numérico, buscar por legajo `id_alumno`.
    """
    active_school = get_request_school(request)
    alumnos_qs = scope_queryset_to_school(
        Alumno.objects.select_related("school", "school_course"),
        active_school,
    )

    try:
        a = _resolve_alumno_by_pk_or_legajo(alumnos_qs, alumno_id)
    except Alumno.DoesNotExist:
        return Response({"detail": "No encontrado"}, status=404)

    # ✅ NUEVO: autorización consistente (incluye preceptor por curso)
    user = request.user
    is_padre = (getattr(a, "padre_id", None) == user.id)
    is_prof_ok = _has_role(request, "Profesores") and _profesor_can_access_alumno(user, a)
    is_prof_or_super = (user.is_superuser or is_prof_ok)
    # Alumno propio:
    # - Vínculo explícito Alumno.usuario (si existe)
    # - Fallback robusto (username==legajo, padre con único hijo, etc.)
    is_alumno_mismo = False
    try:
        is_alumno_mismo = (getattr(a, "usuario_id", None) == user.id)
    except Exception:
        is_alumno_mismo = False
    if not is_alumno_mismo:
        try:
            r = resolve_alumno_for_user(user, school=active_school)
            if r.alumno and r.alumno.id == a.id:
                is_alumno_mismo = True
        except Exception:
            pass
    is_preceptor_ok = (
        _has_role(request, "Directivos")
        or (_has_role(request, "Preceptores") and _preceptor_can_access_alumno(user, a))
    )

    is_school_admin = (
        _has_role(request, "Administradores", "Administrador")
        and SchoolAdmin.objects.filter(admin=user, school=a.school).exists()
    )
    can_edit_ppi = bool(user.is_superuser or is_preceptor_ok or is_school_admin)

    if not (is_padre or is_prof_or_super or is_alumno_mismo or is_preceptor_ok or is_school_admin):
        return Response({"detail": "No autorizado"}, status=403)

    if request.method == "PATCH":
        if not can_edit_ppi:
            return Response({"detail": "No autorizado para modificar PPI."}, status=403)
        # This endpoint only updates the PPI flag; student identity stays untouched.
        if set(request.data) != {"es_ppi"} or not isinstance(request.data.get("es_ppi"), bool):
            return Response({"detail": "Enviá únicamente es_ppi con valor true o false."}, status=400)
        a.es_ppi = request.data["es_ppi"]
        a.save(update_fields=["es_ppi"])

    data = dict(AlumnoFullSerializer(a).data)
    # Keep this flag within the authorized institutional student profile.
    if can_edit_ppi or is_prof_ok:
        data["es_ppi"] = a.es_ppi
        data["can_edit_ppi"] = can_edit_ppi
    return Response(data)


# =========================================================
#  API Notas de un alumno
# =========================================================
@csrf_exempt
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def alumno_notas(request, alumno_id):
    """
    GET /api/alumnos/<alumno_id>/notas/

    Prioridad de resolución:
      1) Si es numérico, buscar por PK (id interno, usado por los links del front).
      2) Si no existe o no es numérico, buscar por legajo `id_alumno`.
    """
    active_school = get_request_school(request)
    alumnos_qs = scope_queryset_to_school(Alumno.objects.all(), active_school)

    try:
        alumno = _resolve_alumno_by_pk_or_legajo(alumnos_qs, alumno_id)
    except Alumno.DoesNotExist:
        return Response({"detail": "Alumno no encontrado"}, status=404)

    user = request.user
    viewer_groups = set(_effective_groups(request))

    # Alumno propio (mismo criterio que en alumno_detalle)
    is_alumno_mismo = (getattr(alumno, "usuario_id", None) == user.id)
    if not is_alumno_mismo and "Alumnos" in viewer_groups:
        try:
            r = resolve_alumno_for_user(user, school=active_school)
            if r.alumno and r.alumno.id == alumno.id:
                is_alumno_mismo = True
        except Exception:
            pass

    # ✅ NUEVO: sumar Preceptores (pero solo si tienen el curso asignado)
    is_preceptor_ok = (
        ("Directivos" in viewer_groups)
        or ("Preceptores" in viewer_groups and _preceptor_can_access_alumno(user, alumno))
    )
    is_prof_ok = ("Profesores" in viewer_groups and _profesor_can_access_alumno(user, alumno))

    # Autorización: superuser, profesores, preceptor por curso, padre o el propio alumno
    if not (
        user.is_superuser
        or is_prof_ok
        or is_preceptor_ok
        or alumno.padre_id == user.id
        or is_alumno_mismo
    ):
        return Response({"detail": "No autorizado"}, status=403)

    qs = scope_queryset_to_school(Nota.objects.filter(alumno=alumno), active_school)
    # Orden consistente: por cuatrimestre y, si existe, por fecha
    if any(f.name == 'fecha' for f in Nota._meta.fields):
        qs = qs.order_by('cuatrimestre', 'fecha', 'materia')
    else:
        qs = qs.order_by('cuatrimestre', 'materia')

    data = NotaPublicSerializer(qs, many=True).data
    return Response({
        "alumno": {"id": alumno.id, "id_alumno": alumno.id_alumno, "nombre": alumno.nombre},
        "notas": data
    })
