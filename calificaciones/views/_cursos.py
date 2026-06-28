# calificaciones/views/_cursos.py
# Endpoint de contexto de curso, catálogos y alumnos por curso

from django.views.decorators.csrf import csrf_exempt

from rest_framework.decorators import (
    api_view, authentication_classes, permission_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..constants import MATERIAS
from ..contexto import resolve_alumno_for_user
from ..course_access import (
    course_ref_matches,
    filter_course_options_by_refs,
    build_course_membership_q,
)
from ..jwt_auth import CookieJWTAuthentication as JWTAuthentication
from ..models import Alumno
from ..schools import (
    get_request_school,
    scope_queryset_to_school,
)
from ..utils_cursos import get_school_course_by_id
from ..models import resolve_school_course_for_value
from ._acceso import (
    _can_access_course_roster,
    _course_option_payload,
    _effective_groups,
    _get_preview_role,
    _has_model_field,
    _has_role,
    _preceptor_assignment_refs,
    _profesor_assignment_refs,
    _profile_assigned_school_courses,
    _public_course_payload,
    _public_course_payload_from_option,
    _resolve_path_course_selection,
    _resolve_request_course_selection,
    _school_course_options_for_ui,
)


# =========================================================
#  Endpoint de contexto de curso para calendario
#      GET /api/mi-curso/  ->  { "school_course_id": 14, "school_course_name": "1A Norte" }
# =========================================================
@csrf_exempt
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mi_curso(request):
    """
    Devuelve el curso asociado al usuario logueado.

    Casos:
    - Alumno: curso del alumno vinculado (resolve_alumno_for_user)
    - Padre: curso del hijo (primero), o seleccionar por ?id_alumno=... o ?alumno_id=...
    - Preceptor: primer curso asignado real en PreceptorCurso
    - Superuser: si está en vista previa, se comporta como ese rol; si no, devuelve el curso pedido por
      `school_course_id`, o cae al primero disponible
    """
    user = request.user
    active_school = get_request_school(request)
    preview_role = _get_preview_role(request)
    from ..user_groups import get_user_group_names
    grupos = [preview_role] if (preview_role and user.is_superuser) else list(get_user_group_names(user))

    curso = None
    school_course = None
    payload = None

    # 1) Alumno
    if "Alumnos" in grupos:
        r = resolve_alumno_for_user(user, school=active_school)
        if r.alumno:
            school_course = getattr(r.alumno, "school_course", None)
            curso = getattr(school_course, "code", None) or getattr(r.alumno, "curso", None)
        elif preview_role and user.is_superuser:
            a0 = scope_queryset_to_school(
                Alumno.objects.select_related("school_course"),
                active_school,
            ).order_by("school_course__sort_order", "curso", "id").first()
            school_course = getattr(a0, "school_course", None) if a0 else None
            curso = getattr(school_course, "code", None) or (getattr(a0, "curso", None) if a0 else None)

    # 2) Padre
    if curso is None and "Padres" in grupos:
        alumno_pk = (request.GET.get("alumno_id") or "").strip()
        legajo = (request.GET.get("id_alumno") or "").strip()
        alumno_qs = scope_queryset_to_school(
            Alumno.objects.select_related("school_course"),
            active_school,
        )

        alumno = None
        if alumno_pk.isdigit():
            try:
                alumno = alumno_qs.get(pk=int(alumno_pk), padre=user) if not preview_role else alumno_qs.get(pk=int(alumno_pk))
            except Exception:
                alumno = None
        elif legajo:
            try:
                alumno = alumno_qs.get(id_alumno=str(legajo), padre=user) if not preview_role else alumno_qs.get(id_alumno=str(legajo))
            except Exception:
                alumno = None

        if alumno is None:
            qs = alumno_qs.filter(padre=user).order_by("curso", "nombre")
            alumno = qs.first() if qs is not None else None
            if alumno is None and preview_role and user.is_superuser:
                a0 = alumno_qs.filter(
                    padre__isnull=False
                ).order_by("padre_id", "curso").first()
                if a0 and a0.padre_id:
                    alumno = (
                        alumno_qs.filter(
                            padre_id=a0.padre_id
                        )
                        .order_by("curso", "nombre")
                        .first()
                    )

        school_course = getattr(alumno, "school_course", None) if alumno else None
        curso = getattr(school_course, "code", None) or (getattr(alumno, "curso", None) if alumno else None)

    # 3) Preceptor / Directivo
    if curso is None and ("Preceptores" in grupos or "Directivos" in grupos):
        if "Preceptores" in grupos:
            assigned_refs = _preceptor_assignment_refs(user, school=active_school)
            assigned_options = (
                filter_course_options_by_refs(_school_course_options_for_ui(school=active_school), assigned_refs)
                if assigned_refs
                else []
            )
            selected_course = _resolve_request_course_selection(
                request,
                school=active_school,
                required=False,
            )
            if selected_course["error"]:
                return Response({"detail": selected_course["error"]}, status=400)
            if assigned_options:
                selected_option = None
                if (selected_course["school_course_id"] or selected_course["course_code"]) and course_ref_matches(
                    assigned_refs,
                    school_course_id=selected_course["school_course_id"],
                    course_code=selected_course["course_code"],
                ):
                    if selected_course["school_course_id"]:
                        selected_option = next(
                            (
                                option
                                for option in assigned_options
                                if option.get("school_course_id") == selected_course["school_course_id"]
                            ),
                            None,
                        )
                    if selected_option is None and selected_course["course_code"]:
                        selected_option = next(
                            (
                                option
                                for option in assigned_options
                                if option.get("code") == selected_course["course_code"]
                            ),
                            None,
                        )
                if selected_option is None:
                    selected_option = assigned_options[0]
                payload = _public_course_payload_from_option(selected_option)
                curso = str(selected_option.get("code") or "").strip().upper() or None

        if (curso is None) and preview_role and user.is_superuser:
            first_course = _school_course_options_for_ui(school=active_school)
            if first_course:
                payload = _public_course_payload_from_option(first_course[0])
                curso = str(first_course[0].get("code") or "").strip().upper() or None
        if curso is None and "Directivos" in grupos:
            first_course = _school_course_options_for_ui(school=active_school)
            if first_course:
                payload = _public_course_payload_from_option(first_course[0])
                curso = str(first_course[0].get("code") or "").strip().upper() or None

    # 4) Superuser sin vista previa: permitir querystring o fallback
    if curso is None and user.is_superuser and not preview_role:
        selected_course = _resolve_request_course_selection(
            request,
            school=active_school,
        )
        if selected_course["error"]:
            return Response({"detail": selected_course["error"]}, status=400)
        if selected_course["school_course"] is not None or selected_course["course_code"]:
            school_course = selected_course["school_course"]
            curso = selected_course["course_code"]
        else:
            first_course = _school_course_options_for_ui(school=active_school)
            if first_course:
                payload = _public_course_payload_from_option(first_course[0])
                curso = str(first_course[0].get("code") or "").strip().upper() or None

    if not curso:
        return Response(
            {
                "detail": "No se pudo resolver el curso para este usuario.",
                "school_course_id": None,
                "school_course_name": None,
            },
            status=200,
        )

    if payload is not None and school_course is None:
        return Response(payload, status=200)

    return Response(
        _public_course_payload(
            school=active_school,
            course_code=curso,
            school_course=school_course,
        ),
        status=200,
    )


# =========================================================
#  Catálogos/Alumnos para "Nueva nota"
# =========================================================
@csrf_exempt
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def notas_catalogos(request):
    """
    Devuelve catálogos base para la pantalla de "Nueva nota".
    - cursos: lista normalizada de `SchoolCourse` para el colegio activo
    - materias: lista desde constants.MATERIAS
    - tipos: (opcional) vacío por ahora; se puede poblar luego si definen choices
    """
    active_school = get_request_school(request)
    cursos = [
        _course_option_payload(option)
        for option in _school_course_options_for_ui(school=active_school)
    ]
    if not request.user.is_superuser:
        if _has_role(request, "Preceptores"):
            assigned_refs = _preceptor_assignment_refs(request.user, school=active_school)
            if not assigned_refs:
                cursos = []
            else:
                cursos = [
                    _course_option_payload(option)
                    for option in filter_course_options_by_refs(
                        _school_course_options_for_ui(school=active_school),
                        assigned_refs,
                    )
                ]
        elif _has_role(request, "Profesores"):
            assigned_refs = _profesor_assignment_refs(request.user, school=active_school)
            if not assigned_refs:
                cursos = []
            else:
                cursos = [
                    _course_option_payload(option)
                    for option in filter_course_options_by_refs(
                        _school_course_options_for_ui(school=active_school),
                        assigned_refs,
                    )
                ]
    materias = list(MATERIAS)
    tipos = []  # futuro: mapear choices de Nota si existen

    return Response({
        "cursos": cursos,
        "materias": materias,
        "tipos": tipos,
    })

def _alumnos_por_curso_qs(curso: str, *, school=None, school_course=None, school_course_id=None):
    curso = str(curso or "").strip().upper()
    resolved_school_course = school_course
    if resolved_school_course is None and school_course_id is not None:
        resolved_school_course = get_school_course_by_id(school_course_id, school=school, include_inactive=True)
    if resolved_school_course is None and school is not None and curso:
        resolved_school_course = resolve_school_course_for_value(school=school, curso=curso)

    if not curso and resolved_school_course is not None:
        curso = str(getattr(resolved_school_course, "code", "") or "").strip().upper()

    if not curso and resolved_school_course is None:
        return Alumno.objects.none()

    course_q = build_course_membership_q(
        school_course_id=getattr(resolved_school_course, "id", None) or school_course_id,
        course_code=curso,
        school_course_field="school_course",
        code_field="curso",
    )
    if course_q is None:
        return Alumno.objects.none()
    return scope_queryset_to_school(Alumno.objects.all(), school).filter(course_q)


def _build_alumnos_payload(qs, *, school=None, course_code="", school_course=None):
    """
    Helper interno: arma el JSON de alumnos para UI.
    (Se usa tanto para querystring como para ruta /curso/<id>/)
    """
    data = []
    for a in qs:
        p = getattr(a, "padre", None)
        padre_nombre = ""
        if p:
            try:
                padre_nombre = (p.get_full_name() or p.username or p.email or "").strip()
            except Exception:
                padre_nombre = getattr(p, "username", "") or getattr(p, "email", "") or ""

        data.append({
            "id": a.id,
            "id_alumno": getattr(a, "id_alumno", None),
            "nombre": a.nombre,
            "apellido": getattr(a, "apellido", "") if _has_model_field(Alumno, "apellido") else "",
            "school_course_id": getattr(a, "school_course_id", None),
            "school_course_name": getattr(getattr(a, "school_course", None), "name", None) or getattr(getattr(a, "school_course", None), "code", None) or a.curso,
            "padre": {
                "id": getattr(p, "id", None) if p else None,
                "username": getattr(p, "username", "") if p else "",
                "first_name": getattr(p, "first_name", "") if p else "",
                "last_name": getattr(p, "last_name", "") if p else "",
                "email": getattr(p, "email", "") if p else "",
                "nombre_completo": padre_nombre,
            }
        })
    payload = {"alumnos": data}
    payload.update(_public_course_payload(school=school, course_code=course_code, school_course=school_course))
    return payload


@csrf_exempt
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def alumnos_por_curso(request):
    """
    GET /api/alumnos/?school_course_id=ID
    Requiere school_course_id para seleccionar curso.
    Devuelve alumnos de un curso, incluyendo datos del padre/tutor para UI.
    """
    active_school = get_request_school(request)
    selected_course = _resolve_request_course_selection(
        request,
        school=active_school,
        required=True,
    )
    if selected_course["error"]:
        return Response({"detail": selected_course["error"]}, status=400)

    curso = selected_course["course_code"]
    school_course = selected_course["school_course"]

    if not _can_access_course_roster(request, curso, school_course=school_course):
        return Response({"detail": "No autorizado para ese curso."}, status=403)

    # ✅ FIX: si Alumno no tiene apellido, no explota
    if _has_model_field(Alumno, "apellido"):
        qs = _alumnos_por_curso_qs(
            curso,
            school=active_school,
            school_course=school_course,
            school_course_id=selected_course["school_course_id"],
        ).order_by("apellido", "nombre")
    else:
        qs = _alumnos_por_curso_qs(
            curso,
            school=active_school,
            school_course=school_course,
            school_course_id=selected_course["school_course_id"],
        ).order_by("nombre")

    return Response(
        _build_alumnos_payload(qs, school=active_school, course_code=curso, school_course=school_course),
        status=200,
    )


# =========================================================
#  Endpoint por path con SchoolCourse:
#      GET /api/alumnos/curso/<school_course_id>/
# =========================================================
@csrf_exempt
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def alumnos_por_curso_path(request, curso: str):
    """
    GET /api/alumnos/curso/<school_course_id>/

    Este endpoint solo acepta ids numéricos de SchoolCourse en la ruta.
    """
    active_school = get_request_school(request)
    selected_course = _resolve_path_course_selection(
        curso,
        school=active_school,
        required=True,
        deprecated_course_error="El código legacy de curso en la ruta está deprecado. Usa school_course_id.",
    )
    if selected_course["error"]:
        return Response({"detail": selected_course["error"]}, status=400)

    course_code = selected_course["course_code"]
    school_course = selected_course["school_course"]

    if not _can_access_course_roster(request, course_code, school_course=school_course):
        return Response({"detail": "No autorizado para ese curso."}, status=403)

    if _has_model_field(Alumno, "apellido"):
        qs = _alumnos_por_curso_qs(
            course_code,
            school=active_school,
            school_course=school_course,
            school_course_id=selected_course["school_course_id"],
        ).order_by("apellido", "nombre")
    else:
        qs = _alumnos_por_curso_qs(
            course_code,
            school=active_school,
            school_course=school_course,
            school_course_id=selected_course["school_course_id"],
        ).order_by("nombre")

    return Response(
        _build_alumnos_payload(
            qs,
            school=active_school,
            course_code=course_code,
            school_course=school_course,
        ),
        status=200,
    )


def _resolve_alumno_by_pk_or_legajo(alumnos_qs, alumno_id):
    raw_id = str(alumno_id or "").strip()
    if not raw_id:
        raise Alumno.DoesNotExist

    if raw_id.isdigit():
        try:
            return alumnos_qs.get(pk=int(raw_id))
        except Alumno.DoesNotExist:
            pass

    try:
        return alumnos_qs.get(id_alumno__iexact=raw_id)
    except Alumno.DoesNotExist:
        if raw_id.isdigit():
            raise
        raise
