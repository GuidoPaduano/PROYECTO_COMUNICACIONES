from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .jwt_auth import CookieJWTAuthentication as JWTAuthentication
from .models import Alumno, SchoolCourse
from .models_preceptores import PreceptorCurso, ProfesorCurso, SchoolAdmin
from .schools import get_request_school, school_to_dict

User = get_user_model()

STAFF_ROLE_NAMES = ("Profesores", "Preceptores", "Directivos")
USER_ROLE_NAMES = ("Alumnos", "Padres", "Profesores", "Preceptores", "Directivos", "Administradores")


def _is_school_admin(user) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    groups = set(_get_user_group_names(user))
    if not groups.intersection({"Administradores", "Administrador"}):
        return False
    try:
        return SchoolAdmin.objects.filter(admin=user).exists()
    except Exception:
        return False


def _require_school_admin(request):
    if not _is_school_admin(getattr(request, "user", None)):
        return Response({"detail": "No autorizado."}, status=403)
    return None


def _normalize_staff_role(raw_value: str = "") -> str:
    value = str(raw_value or "").strip()
    return value if value in STAFF_ROLE_NAMES else ""


def _normalize_user_role(raw_value: str = "") -> str:
    value = str(raw_value or "").strip()
    return value if value in USER_ROLE_NAMES else ""


def _normalize_course_ids(raw_value) -> list[int]:
    if not isinstance(raw_value, list):
        return []
    normalized: list[int] = []
    seen: set[int] = set()
    for item in raw_value:
        try:
            course_id = int(item)
        except (TypeError, ValueError):
            continue
        if course_id <= 0 or course_id in seen:
            continue
        seen.add(course_id)
        normalized.append(course_id)
    return normalized


def _normalize_user_ids(raw_value) -> list[int]:
    if not isinstance(raw_value, list):
        return []
    normalized: list[int] = []
    seen: set[int] = set()
    for item in raw_value:
        try:
            user_id = int(item)
        except (TypeError, ValueError):
            continue
        if user_id <= 0 or user_id in seen:
            continue
        seen.add(user_id)
        normalized.append(user_id)
    return normalized


def _normalize_single_id(raw_value):
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _full_name(user) -> str:
    return " ".join(
        part for part in [str(getattr(user, "first_name", "") or "").strip(), str(getattr(user, "last_name", "") or "").strip()] if part
    ).strip()


def _get_user_group_names(user) -> list[str]:
    try:
        return list(user.groups.order_by("name").values_list("name", flat=True))
    except Exception:
        return []


def _serialize_course(course) -> dict:
    return {
        "id": course.id,
        "code": str(getattr(course, "code", "") or "").strip(),
        "name": str(getattr(course, "name", "") or "").strip(),
        "is_active": bool(getattr(course, "is_active", True)),
    }


def _serialize_student(student) -> dict:
    school_course = getattr(student, "school_course", None)
    return {
        "id": student.id,
        "id_alumno": str(getattr(student, "id_alumno", "") or "").strip(),
        "nombre": str(getattr(student, "nombre", "") or "").strip(),
        "apellido": str(getattr(student, "apellido", "") or "").strip(),
        "full_name": " ".join(
            part
            for part in [
                str(getattr(student, "nombre", "") or "").strip(),
                str(getattr(student, "apellido", "") or "").strip(),
            ]
            if part
        ).strip(),
        "school_course_id": getattr(student, "school_course_id", None),
        "school_course_label": " - ".join(
            part
            for part in [
                str(getattr(school_course, "code", "") or "").strip(),
                str(getattr(school_course, "name", "") or "").strip(),
            ]
            if part
        ).strip()
        or str(getattr(student, "curso", "") or "").strip(),
        "has_user": bool(getattr(student, "usuario_id", None)),
        "has_parent": bool(getattr(student, "padre_id", None)),
    }


def _serialize_staff_user(*, user, school, preceptor_map, profesor_map) -> dict:
    preceptor_courses = preceptor_map.get(user.id, [])
    profesor_courses = profesor_map.get(user.id, [])

    assignment_role = ""
    assigned_courses = []
    if profesor_courses:
        assignment_role = "Profesores"
        assigned_courses = profesor_courses
    elif preceptor_courses:
        assignment_role = "Preceptores"
        assigned_courses = preceptor_courses

    groups = _get_user_group_names(user)
    staff_role = assignment_role or next((name for name in STAFF_ROLE_NAMES if name in groups), "")

    return {
        "id": user.id,
        "username": user.username,
        "full_name": _full_name(user),
        "email": str(getattr(user, "email", "") or "").strip(),
        "is_active": bool(getattr(user, "is_active", True)),
        "groups": groups,
        "staff_role": staff_role,
        "assigned_school_courses": [_serialize_course(course) for course in assigned_courses],
        "school": school_to_dict(school),
    }


def _build_assignment_map(*, school, role: str) -> dict[int, list[SchoolCourse]]:
    if role == "Profesores":
        rows = (
            ProfesorCurso.objects.select_related("school_course")
            .filter(school=school, school_course__isnull=False)
            .order_by("school_course__sort_order", "school_course__name", "id")
        )
        user_field = "profesor_id"
    else:
        rows = (
            PreceptorCurso.objects.select_related("school_course")
            .filter(school=school, school_course__isnull=False)
            .order_by("school_course__sort_order", "school_course__name", "id")
        )
        user_field = "preceptor_id"

    assignments: dict[int, list[SchoolCourse]] = {}
    for row in rows:
        user_id = getattr(row, user_field, None)
        course = getattr(row, "school_course", None)
        if user_id is None or course is None:
            continue
        assignments.setdefault(user_id, []).append(course)
    return assignments


def _list_staff_users(*, school, query: str = "") -> list[User]:
    preceptor_user_ids = list(
        PreceptorCurso.objects.filter(school=school).values_list("preceptor_id", flat=True).distinct()
    )
    profesor_user_ids = list(
        ProfesorCurso.objects.filter(school=school).values_list("profesor_id", flat=True).distinct()
    )

    base_filter = Q(id__in=preceptor_user_ids) | Q(id__in=profesor_user_ids) | Q(groups__name__in=STAFF_ROLE_NAMES)
    qs = User.objects.exclude(is_superuser=True)

    if query:
        qs = qs.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        )
    else:
        qs = qs.filter(base_filter)

    return list(qs.order_by("first_name", "last_name", "username", "id")[:100])


def _set_staff_role_group(*, user, role: str):
    current = set(_get_user_group_names(user))
    for group_name in STAFF_ROLE_NAMES:
        if group_name in current and group_name != role:
            try:
                group = Group.objects.get(name=group_name)
                user.groups.remove(group)
            except Group.DoesNotExist:
                continue

    if role:
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)


def _set_user_role_group(*, user, role: str):
    current = set(_get_user_group_names(user))
    for group_name in USER_ROLE_NAMES:
        if group_name in current and group_name != role:
            try:
                group = Group.objects.get(name=group_name)
                user.groups.remove(group)
            except Group.DoesNotExist:
                continue

    if role:
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)


def _replace_profesor_assignments(*, user, school, courses: list[SchoolCourse]):
    PreceptorCurso.objects.filter(preceptor=user, school=school).delete()
    desired_ids = {course.id for course in courses}
    existing = {
        row.school_course_id: row
        for row in ProfesorCurso.objects.filter(profesor=user, school=school)
    }

    stale_ids = [row.id for course_id, row in existing.items() if course_id not in desired_ids]
    if stale_ids:
        ProfesorCurso.objects.filter(id__in=stale_ids).delete()

    pending = []
    for course in courses:
        if course.id in existing:
            continue
        pending.append(
            ProfesorCurso(
                school=school,
                school_course=course,
                profesor=user,
                curso=course.code,
            )
        )
    if pending:
        ProfesorCurso.objects.bulk_create(pending)


def _replace_preceptor_assignments(*, user, school, courses: list[SchoolCourse]):
    ProfesorCurso.objects.filter(profesor=user, school=school).delete()
    desired_ids = {course.id for course in courses}
    existing = {
        row.school_course_id: row
        for row in PreceptorCurso.objects.filter(preceptor=user, school=school)
    }

    stale_ids = [row.id for course_id, row in existing.items() if course_id not in desired_ids]
    if stale_ids:
        PreceptorCurso.objects.filter(id__in=stale_ids).delete()

    pending = []
    for course in courses:
        if course.id in existing:
            continue
        pending.append(
            PreceptorCurso(
                school=school,
                school_course=course,
                preceptor=user,
                curso=course.code,
            )
        )
    if pending:
        PreceptorCurso.objects.bulk_create(pending)


def _set_single_course_assignment(*, user, school, course: SchoolCourse, role: str):
    _set_staff_role_group(user=user, role=role)
    if role == "Profesores":
        PreceptorCurso.objects.filter(preceptor=user, school=school).delete()
        ProfesorCurso.objects.get_or_create(
            school=school,
            school_course=course,
            profesor=user,
            defaults={"curso": course.code},
        )
    elif role == "Preceptores":
        ProfesorCurso.objects.filter(profesor=user, school=school).delete()
        PreceptorCurso.objects.get_or_create(
            school=school,
            school_course=course,
            preceptor=user,
            defaults={"curso": course.code},
        )


def _remove_single_course_assignment(*, user, school, course: SchoolCourse, role: str):
    if role == "Profesores":
        ProfesorCurso.objects.filter(profesor=user, school=school, school_course=course).delete()
    elif role == "Preceptores":
        PreceptorCurso.objects.filter(preceptor=user, school=school, school_course=course).delete()


def _validate_new_user_payload(payload) -> dict:
    username = str(payload.get("username") or "").strip()
    first_name = str(payload.get("first_name") or "").strip()
    last_name = str(payload.get("last_name") or "").strip()
    email = str(payload.get("email") or "").strip()
    password = str(payload.get("password") or "")
    password_confirm = str(payload.get("password_confirm") or "")
    role = _normalize_user_role(payload.get("role") or "")
    course_ids = _normalize_course_ids(payload.get("school_course_ids"))
    alumno_id = _normalize_single_id(payload.get("alumno_id"))
    alumno_ids = _normalize_user_ids(payload.get("alumno_ids"))

    if not first_name:
        raise ValueError("El nombre es obligatorio.")
    if not last_name:
        raise ValueError("El apellido es obligatorio.")
    if not username:
        raise ValueError("El nombre de usuario es obligatorio.")
    if not role:
        raise ValueError("Selecciona un tipo de usuario valido.")
    if not password:
        raise ValueError("La contraseña es obligatoria.")
    if password != password_confirm:
        raise ValueError("Las contraseñas no coinciden.")
    if User.objects.filter(username__iexact=username).exists():
        raise ValueError("Ya existe un usuario con ese nombre de usuario.")
    if email and User.objects.filter(email__iexact=email).exists():
        raise ValueError("Ya existe un usuario con ese correo.")
    try:
        validate_password(password)
    except DjangoValidationError as exc:
        raise ValueError(" ".join(str(message) for message in getattr(exc, "messages", []) if message))

    return {
        "username": username,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "password": password,
        "role": role,
        "school_course_ids": course_ids,
        "alumno_id": alumno_id,
        "alumno_ids": alumno_ids,
    }


def _build_user_creation_payload(*, school):
    courses = list(
        SchoolCourse.objects.filter(school=school, is_active=True).order_by("sort_order", "name", "id")
    )
    students = list(
        Alumno.objects.select_related("school_course")
        .filter(school=school)
        .order_by("school_course__sort_order", "apellido", "nombre", "id")
    )
    return {
        "school": school_to_dict(school),
        "courses": [_serialize_course(course) for course in courses],
        "students": [_serialize_student(student) for student in students],
        "role_options": [
            {"value": "Alumnos", "label": "Alumno/a", "description": "Crea el acceso de un alumno y permite vincularlo a su legajo."},
            {"value": "Padres", "label": "Padre, madre o tutor", "description": "Crea un acceso familiar y permite asociarlo a uno o mas alumnos."},
            {"value": "Profesores", "label": "Profesor/a", "description": "Alta de docente con asignacion opcional a cursos del colegio."},
            {"value": "Preceptores", "label": "Preceptor/a", "description": "Alta de preceptor con asignacion opcional a cursos del colegio."},
            {"value": "Directivos", "label": "Directivo/a", "description": "Alta de personal institucional sin cursos obligatorios."},
            {"value": "Administradores", "label": "Administrador/a de colegio", "description": "Habilita el acceso al admin del colegio activo."},
        ],
    }


def _serialize_created_user(*, user, school):
    preceptor_map = _build_assignment_map(school=school, role="Preceptores")
    profesor_map = _build_assignment_map(school=school, role="Profesores")
    return _serialize_staff_user(
        user=user,
        school=school,
        preceptor_map=preceptor_map,
        profesor_map=profesor_map,
    )


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def admin_staff_overview(request):
    denied = _require_school_admin(request)
    if denied is not None:
        return denied

    active_school = get_request_school(request)
    if active_school is None:
        return Response({"detail": "No hay un colegio activo seleccionado."}, status=400)

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
            return Response({"detail": "Selecciona el alumno que se va a vincular al usuario."}, status=400)
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
            return Response({"detail": "Uno o mas alumnos seleccionados no pertenecen al colegio activo."}, status=400)
        occupied = [student.id_alumno for student in parent_students if getattr(student, "padre_id", None)]
        if occupied:
            return Response(
                {"detail": f"Uno o mas alumnos ya tienen tutor vinculado ({', '.join(occupied[:3])})."},
                status=400,
            )

    selected_courses = []
    if data["school_course_ids"]:
        selected_courses = list(
            SchoolCourse.objects.filter(school=active_school, is_active=True, id__in=data["school_course_ids"]).order_by("sort_order", "name", "id")
        )
        if len(selected_courses) != len(data["school_course_ids"]):
            return Response({"detail": "Uno o mas cursos no pertenecen al colegio activo."}, status=400)

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
        return Response({"detail": "Selecciona al menos un curso para ese rol."}, status=400)
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
        _set_staff_role_group(user=target, role=role)
        if role == "Profesores":
            _replace_profesor_assignments(user=target, school=active_school, courses=courses)
        elif role == "Preceptores":
            _replace_preceptor_assignments(user=target, school=active_school, courses=courses)
        else:
            ProfesorCurso.objects.filter(profesor=target, school=active_school).delete()
            PreceptorCurso.objects.filter(preceptor=target, school=active_school).delete()

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
