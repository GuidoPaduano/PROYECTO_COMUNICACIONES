from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..jwt_auth import CookieJWTAuthentication as JWTAuthentication
from ..models import Alumno, SchoolCourse
from ..models_preceptores import PreceptorCurso, ProfesorCurso, SchoolAdmin, SchoolMembership
from ..schools import (
    clear_user_school_resolution_cache,
    get_request_school,
    school_to_dict,
)
from ._helpers import (
    STAFF_ROLE_NAMES,
    _build_assignment_map,
    _build_user_creation_payload,
    _build_user_directory_payload,
    _clear_parent_children_cache,
    _contains_digit,
    _list_staff_users,
    _normalize_course_ids,
    _normalize_single_id,
    _normalize_staff_role,
    _normalize_user_ids,
    _remove_single_course_assignment,
    _replace_preceptor_assignments,
    _replace_profesor_assignments,
    _require_school_admin,
    _resolve_requested_admin_school,
    _serialize_course,
    _serialize_created_user,
    _serialize_staff_user,
    _set_single_course_assignment,
    _set_staff_role_group,
    _set_user_role_group,
    _user_belongs_to_school,
    _user_is_school_admin_for,
    _validate_new_user_payload,
)

User = get_user_model()


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def admin_staff_overview(request):
    denied = _require_school_admin(request)
    if denied is not None:
        return denied

    active_school, denied = _resolve_requested_admin_school(request)
    if denied is not None:
        return denied

    query = str(request.GET.get("q") or "").strip()
    courses = list(
        SchoolCourse.objects.filter(school=active_school, is_active=True).order_by("sort_order", "name", "id")
    )
    users = _list_staff_users(school=active_school, query=query)
    preceptor_map = _build_assignment_map(school=active_school, role="Preceptores")
    profesor_map = _build_assignment_map(school=active_school, role="Profesores")

    return Response(
        {
            "school": school_to_dict(active_school),
            "courses": [_serialize_course(course) for course in courses],
            "role_options": list(STAFF_ROLE_NAMES),
            "users": [
                _serialize_staff_user(
                    user=user,
                    school=active_school,
                    preceptor_map=preceptor_map,
                    profesor_map=profesor_map,
                )
                for user in users
            ],
        }
    )


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def admin_school_user_directory(request):
    denied = _require_school_admin(request)
    if denied is not None:
        return denied

    active_school, denied = _resolve_requested_admin_school(request)
    if denied is not None:
        return denied

    return Response(_build_user_directory_payload(school=active_school))


@api_view(["PATCH"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def admin_school_user_update(request, user_id: int):
    denied = _require_school_admin(request)
    if denied is not None:
        return denied

    active_school, denied = _resolve_requested_admin_school(request)
    if denied is not None:
        return denied

    target = User.objects.filter(pk=user_id).exclude(is_superuser=True).first()
    if target is None or not _user_belongs_to_school(user=target, school=active_school):
        return Response({"detail": "Usuario no encontrado en el colegio activo."}, status=404)

    first_name = str(request.data.get("first_name") or "").strip()
    last_name = str(request.data.get("last_name") or "").strip()
    email = str(request.data.get("email") or "").strip()

    if not first_name:
        return Response({"detail": "El nombre es obligatorio."}, status=400)
    if not last_name:
        return Response({"detail": "El apellido es obligatorio."}, status=400)
    if _contains_digit(first_name):
        return Response({"detail": "El nombre no puede contener números."}, status=400)
    if _contains_digit(last_name):
        return Response({"detail": "El apellido no puede contener números."}, status=400)
    if email and User.objects.filter(email__iexact=email).exclude(pk=target.pk).exists():
        return Response({"detail": "Ya existe un usuario con ese correo."}, status=400)

    target.first_name = first_name
    target.last_name = last_name
    target.email = email
    target.save(update_fields=["first_name", "last_name", "email"])

    return Response(
        {
            "detail": "Usuario actualizado correctamente.",
            "directory": _build_user_directory_payload(school=active_school),
        }
    )


@api_view(["PATCH"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def admin_parent_children_update(request, user_id: int):
    denied = _require_school_admin(request)
    if denied is not None:
        return denied

    active_school = get_request_school(request)
    if active_school is None:
        return Response({"detail": "No hay un colegio activo seleccionado."}, status=400)
    if not _user_is_school_admin_for(active_school, getattr(request, "user", None)):
        return Response({"detail": "No autorizado para el colegio activo."}, status=403)

    parent = User.objects.filter(pk=user_id, groups__name="Padres").exclude(is_superuser=True).first()
    if parent is None:
        return Response({"detail": "Padre no encontrado."}, status=404)

    raw_ids = request.data.get("alumno_ids")
    if raw_ids is None:
        raw_ids = request.data.get("alumno_id")
    student_ids = _normalize_user_ids(raw_ids) if isinstance(raw_ids, list) else []
    if not student_ids:
        single_id = _normalize_single_id(raw_ids)
        if single_id is not None:
            student_ids = [single_id]
    if not student_ids:
        return Response({"detail": "Seleccioná al menos un alumno para vincular."}, status=400)

    students = list(
        Alumno.objects.filter(pk__in=student_ids, school=active_school).order_by("apellido", "nombre", "id")
    )
    if len(students) != len(student_ids):
        return Response({"detail": "Uno o más alumnos seleccionados no pertenecen al colegio activo."}, status=400)

    occupied = [
        student.id_alumno
        for student in students
        if getattr(student, "padre_id", None) and getattr(student, "padre_id", None) != parent.id
    ]
    if occupied:
        return Response(
            {"detail": f"Uno o más alumnos ya tienen tutor vinculado ({', '.join(occupied[:3])})."},
            status=400,
        )

    with transaction.atomic():
        Alumno.objects.filter(pk__in=[student.id for student in students], school=active_school).update(padre=parent)

    _clear_parent_children_cache(parent_id=parent.id, school_id=getattr(active_school, "id", None))

    return Response(
        {
            "detail": "Vínculo actualizado correctamente.",
            "directory": _build_user_directory_payload(school=active_school),
        }
    )


@api_view(["GET", "POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def admin_user_create(request):
    denied = _require_school_admin(request)
    if denied is not None:
        return denied

    active_school = get_request_school(request)
    if active_school is None:
        return Response({"detail": "No hay un colegio activo seleccionado."}, status=400)

    if request.method == "GET":
        return Response(_build_user_creation_payload(school=active_school))

    payload = request.data or {}
    try:
        data = _validate_new_user_payload(payload)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=400)

    linked_student = None
    if data["role"] == "Alumnos":
        if data["alumno_id"] is None:
            return Response({"detail": "Seleccioná el alumno que se va a vincular al usuario."}, status=400)
        linked_student = (
            Alumno.objects.select_related("school_course")
            .filter(pk=data["alumno_id"], school=active_school)
            .first()
        )
        if linked_student is None:
            return Response({"detail": "El alumno seleccionado no pertenece al colegio activo."}, status=400)
        if getattr(linked_student, "usuario_id", None):
            return Response({"detail": "Ese alumno ya tiene un usuario vinculado."}, status=400)

    parent_students = []
    if data["role"] == "Padres" and data["alumno_ids"]:
        parent_students = list(
            Alumno.objects.filter(pk__in=data["alumno_ids"], school=active_school).order_by("apellido", "nombre", "id")
        )
        if len(parent_students) != len(data["alumno_ids"]):
            return Response({"detail": "Uno o más alumnos seleccionados no pertenecen al colegio activo."}, status=400)
        occupied = [student.id_alumno for student in parent_students if getattr(student, "padre_id", None)]
        if occupied:
            return Response(
                {"detail": f"Uno o más alumnos ya tienen tutor vinculado ({', '.join(occupied[:3])})."},
                status=400,
            )

    selected_courses = []
    if data["school_course_ids"]:
        selected_courses = list(
            SchoolCourse.objects.filter(school=active_school, is_active=True, id__in=data["school_course_ids"]).order_by("sort_order", "name", "id")
        )
        if len(selected_courses) != len(data["school_course_ids"]):
            return Response({"detail": "Uno o más cursos no pertenecen al colegio activo."}, status=400)

    with transaction.atomic():
        created_user = User.objects.create_user(
            username=data["username"],
            email=data["email"],
            password=data["password"],
            first_name=data["first_name"],
            last_name=data["last_name"],
        )
        _set_user_role_group(user=created_user, role=data["role"])

        if data["role"] == "Administradores":
            SchoolAdmin.objects.get_or_create(school=active_school, admin=created_user)
        elif data["role"] == "Directivos":
            SchoolMembership.objects.get_or_create(school=active_school, user=created_user)
        elif data["role"] == "Profesores":
            _replace_profesor_assignments(user=created_user, school=active_school, courses=selected_courses)
        elif data["role"] == "Preceptores":
            _replace_preceptor_assignments(user=created_user, school=active_school, courses=selected_courses)
        elif data["role"] == "Alumnos" and linked_student is not None:
            linked_student.usuario = created_user
            linked_student.save(update_fields=["usuario"])
        elif data["role"] == "Padres" and parent_students:
            Alumno.objects.filter(pk__in=[student.id for student in parent_students]).update(padre=created_user)

    return Response(
        {
            "detail": "Usuario creado correctamente.",
            "user": _serialize_created_user(user=created_user, school=active_school),
        },
        status=201,
    )


@api_view(["PATCH"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def admin_staff_update(request, user_id: int):
    denied = _require_school_admin(request)
    if denied is not None:
        return denied

    active_school = get_request_school(request)
    if active_school is None:
        return Response({"detail": "No hay un colegio activo seleccionado."}, status=400)

    target = User.objects.filter(pk=user_id).exclude(is_superuser=True).first()
    if target is None:
        return Response({"detail": "Usuario no encontrado."}, status=404)

    payload = request.data or {}
    role = _normalize_staff_role(payload.get("staff_role") or "")
    course_ids = _normalize_course_ids(payload.get("school_course_ids"))

    if role in {"Profesores", "Preceptores"} and not course_ids:
        return Response({"detail": "Seleccioná al menos un curso para ese rol."}, status=400)
    if role not in {"Profesores", "Preceptores"} and course_ids:
        return Response({"detail": "Solo profesores y preceptores admiten asignaciones de cursos."}, status=400)

    courses = []
    if course_ids:
        courses = list(
            SchoolCourse.objects.filter(school=active_school, is_active=True, id__in=course_ids).order_by("sort_order", "name", "id")
        )
        if len(courses) != len(course_ids):
            return Response({"detail": "Uno o más cursos no pertenecen al colegio activo."}, status=400)

    with transaction.atomic():
        if role == "Directivos":
            SchoolMembership.objects.get_or_create(school=active_school, user=target)
        else:
            SchoolMembership.objects.filter(school=active_school, user=target).delete()
        _set_staff_role_group(user=target, role=role)
        if role == "Profesores":
            _replace_profesor_assignments(user=target, school=active_school, courses=courses)
        elif role == "Preceptores":
            _replace_preceptor_assignments(user=target, school=active_school, courses=courses)
        else:
            ProfesorCurso.objects.filter(profesor=target, school=active_school).delete()
            PreceptorCurso.objects.filter(preceptor=target, school=active_school).delete()
        clear_user_school_resolution_cache(target)

    preceptor_map = _build_assignment_map(school=active_school, role="Preceptores")
    profesor_map = _build_assignment_map(school=active_school, role="Profesores")
    return Response(
        {
            "user": _serialize_staff_user(
                user=target,
                school=active_school,
                preceptor_map=preceptor_map,
                profesor_map=profesor_map,
            )
        }
    )


@api_view(["PATCH"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def admin_staff_course_update(request, course_id: int):
    denied = _require_school_admin(request)
    if denied is not None:
        return denied

    active_school = get_request_school(request)
    if active_school is None:
        return Response({"detail": "No hay un colegio activo seleccionado."}, status=400)

    course = SchoolCourse.objects.filter(school=active_school, is_active=True, pk=course_id).first()
    if course is None:
        return Response({"detail": "Curso no encontrado en el colegio activo."}, status=404)

    payload = request.data or {}
    role = _normalize_staff_role(payload.get("staff_role") or "")
    user_ids = _normalize_user_ids(payload.get("user_ids"))

    if role not in {"Profesores", "Preceptores"}:
        return Response({"detail": "La asignación masiva por curso solo admite profesores o preceptores."}, status=400)

    users = list(User.objects.filter(id__in=user_ids).exclude(is_superuser=True))
    if len(users) != len(user_ids):
        return Response({"detail": "Uno o más usuarios no existen o no son editables."}, status=400)

    if role == "Profesores":
        existing_ids = set(
            ProfesorCurso.objects.filter(school=active_school, school_course=course).values_list("profesor_id", flat=True)
        )
    else:
        existing_ids = set(
            PreceptorCurso.objects.filter(school=active_school, school_course=course).values_list("preceptor_id", flat=True)
        )

    desired_ids = set(user_ids)
    add_ids = desired_ids - existing_ids
    remove_ids = existing_ids - desired_ids

    with transaction.atomic():
        user_map = {user.id: user for user in users}
        for user_id in add_ids:
            user = user_map.get(user_id)
            if user is None:
                continue
            _set_single_course_assignment(user=user, school=active_school, course=course, role=role)

        for user_id in remove_ids:
            user = User.objects.filter(pk=user_id).exclude(is_superuser=True).first()
            if user is None:
                continue
            _remove_single_course_assignment(user=user, school=active_school, course=course, role=role)

    preceptor_map = _build_assignment_map(school=active_school, role="Preceptores")
    profesor_map = _build_assignment_map(school=active_school, role="Profesores")
    users = _list_staff_users(school=active_school, query="")
    return Response(
        {
            "course": _serialize_course(course),
            "users": [
                _serialize_staff_user(
                    user=user,
                    school=active_school,
                    preceptor_map=preceptor_map,
                    profesor_map=profesor_map,
                )
                for user in users
            ],
        }
    )
