from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.cache import cache
from django.db.models import Q
from rest_framework.response import Response

from ..models import Alumno, SchoolCourse
from ..models_preceptores import PreceptorCurso, ProfesorCurso, SchoolAdmin, SchoolMembership
from ..schools import (
    get_request_school,
    get_requested_school_identifier,
    get_school_by_identifier,
    school_to_dict,
)

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


def _contains_digit(raw_value: str = "") -> bool:
    return any(char.isdigit() for char in str(raw_value or ""))


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


def _serialize_directory_user(*, user, assigned_courses=None) -> dict:
    courses = assigned_courses or []
    return {
        "id": user.id,
        "username": user.username,
        "full_name": _full_name(user) or user.username,
        "first_name": str(getattr(user, "first_name", "") or "").strip(),
        "last_name": str(getattr(user, "last_name", "") or "").strip(),
        "email": str(getattr(user, "email", "") or "").strip(),
        "is_active": bool(getattr(user, "is_active", True)),
        "groups": _get_user_group_names(user),
        "assigned_school_courses": [_serialize_course(course) for course in courses],
    }


def _serialize_directory_student(student) -> dict:
    school_course = getattr(student, "school_course", None)
    linked_user = getattr(student, "usuario", None)
    parent_user = getattr(student, "padre", None)
    return {
        "id": student.id,
        "id_alumno": str(getattr(student, "id_alumno", "") or "").strip(),
        "full_name": _serialize_student(student)["full_name"],
        "nombre": str(getattr(student, "nombre", "") or "").strip(),
        "apellido": str(getattr(student, "apellido", "") or "").strip(),
        "course_id": getattr(student, "school_course_id", None),
        "course_code": str(getattr(school_course, "code", "") or "").strip(),
        "course_name": str(getattr(school_course, "name", "") or "").strip(),
        "has_linked_user": bool(getattr(student, "usuario_id", None)),
        "has_parent": bool(getattr(student, "padre_id", None)),
        "linked_user": None
        if linked_user is None
        else {
            "id": linked_user.id,
            "username": linked_user.username,
            "full_name": _full_name(linked_user) or linked_user.username,
            "email": str(getattr(linked_user, "email", "") or "").strip(),
            "is_active": bool(getattr(linked_user, "is_active", True)),
        },
        "parent_user": None
        if parent_user is None
        else {
            "id": parent_user.id,
            "username": parent_user.username,
            "full_name": _full_name(parent_user) or parent_user.username,
            "email": str(getattr(parent_user, "email", "") or "").strip(),
            "is_active": bool(getattr(parent_user, "is_active", True)),
        },
    }


def _serialize_directory_parent(*, user, children=None) -> dict:
    linked_children = children or []
    return {
        **_serialize_directory_user(user=user),
        "children_count": len(linked_children),
        "children": [_serialize_directory_student(child) for child in linked_children],
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


def _clear_parent_children_cache(*, parent_id, school_id):
    try:
        cache.delete(f"mis_hijos:user:{parent_id or 'x'}:school:{school_id or 'none'}:super:0")
        cache.delete(f"mis_hijos:user:{parent_id or 'x'}:school:{school_id or 'none'}:super:1")
    except Exception:
        pass


def _user_is_school_admin_for(school, user) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    return SchoolAdmin.objects.filter(school=school, admin=user).exists()


def _user_belongs_to_school(*, user, school) -> bool:
    user_id = getattr(user, "id", None)
    if user_id is None or school is None:
        return False
    return any(
        (
            SchoolAdmin.objects.filter(school=school, admin_id=user_id).exists(),
            SchoolMembership.objects.filter(school=school, user_id=user_id).exists(),
            ProfesorCurso.objects.filter(school=school, profesor_id=user_id).exists(),
            PreceptorCurso.objects.filter(school=school, preceptor_id=user_id).exists(),
            Alumno.objects.filter(school=school, usuario_id=user_id).exists(),
            Alumno.objects.filter(school=school, padre_id=user_id).exists(),
        )
    )


def _resolve_requested_admin_school(request):
    requested = get_requested_school_identifier(request)
    if requested:
        school = get_school_by_identifier(requested)
        if school is None:
            return None, Response({"detail": "Colegio no encontrado."}, status=404)
        if not _user_is_school_admin_for(school, getattr(request, "user", None)):
            return None, Response({"detail": "No autorizado para el colegio activo."}, status=403)
        return school, None

    active_school = get_request_school(request)
    if active_school is None:
        return None, Response({"detail": "No hay un colegio activo seleccionado."}, status=400)
    if not _user_is_school_admin_for(active_school, getattr(request, "user", None)):
        return None, Response({"detail": "No autorizado para el colegio activo."}, status=403)
    return active_school, None


def _build_user_directory_payload(*, school) -> dict:
    profesor_map = _build_assignment_map(school=school, role="Profesores")
    preceptor_map = _build_assignment_map(school=school, role="Preceptores")

    profesores = list(
        User.objects.filter(id__in=profesor_map.keys())
        .exclude(is_superuser=True)
        .order_by("first_name", "last_name", "username", "id")
    )
    preceptores = list(
        User.objects.filter(id__in=preceptor_map.keys())
        .exclude(is_superuser=True)
        .order_by("first_name", "last_name", "username", "id")
    )
    directivos = list(
        User.objects.filter(groups__name="Directivos", school_memberships__school=school)
        .exclude(is_superuser=True)
        .distinct()
        .order_by("first_name", "last_name", "username", "id")
    )
    alumnos = list(
        Alumno.objects.select_related("school_course", "usuario", "padre")
        .filter(school=school)
        .order_by("school_course__sort_order", "school_course__name", "apellido", "nombre", "id")
    )
    parent_group_ids = User.objects.filter(groups__name="Padres").values_list("id", flat=True)
    parent_ids = {
        int(parent_id)
        for parent_id in Alumno.objects.filter(school=school, padre_id__isnull=False).values_list("padre_id", flat=True)
        if parent_id is not None
    }
    parent_ids.update(int(user_id) for user_id in parent_group_ids if user_id is not None)
    padres = list(
        User.objects.filter(id__in=parent_ids)
        .exclude(is_superuser=True)
        .order_by("first_name", "last_name", "username", "id")
    )
    children_by_parent: dict[int, list[Alumno]] = {}
    for alumno in alumnos:
        parent_id = getattr(alumno, "padre_id", None)
        if parent_id is None:
            continue
        children_by_parent.setdefault(parent_id, []).append(alumno)

    grouped_students: dict[int | str, dict] = {}
    for alumno in alumnos:
        school_course = getattr(alumno, "school_course", None)
        course_id = getattr(alumno, "school_course_id", None)
        key = course_id if course_id is not None else f"legacy:{getattr(alumno, 'curso', '')}"
        if key not in grouped_students:
            grouped_students[key] = {
                "course": {
                    "id": course_id,
                    "code": str(getattr(school_course, "code", "") or getattr(alumno, "curso", "") or "").strip(),
                    "name": str(getattr(school_course, "name", "") or "").strip(),
                    "is_active": bool(getattr(school_course, "is_active", True)) if school_course is not None else True,
                },
                "students": [],
            }
        grouped_students[key]["students"].append(_serialize_directory_student(alumno))

    return {
        "school": school_to_dict(school),
        "profesores": [
            _serialize_directory_user(user=user, assigned_courses=profesor_map.get(user.id, []))
            for user in profesores
        ],
        "preceptores": [
            _serialize_directory_user(user=user, assigned_courses=preceptor_map.get(user.id, []))
            for user in preceptores
        ],
        "directivos": [
            _serialize_directory_user(user=user, assigned_courses=[])
            for user in directivos
        ],
        "padres": [
            _serialize_directory_parent(user=user, children=children_by_parent.get(user.id, []))
            for user in padres
        ],
        "alumnos_por_curso": list(grouped_students.values()),
        "students_without_parent": [
            _serialize_directory_student(alumno)
            for alumno in alumnos
            if getattr(alumno, "padre_id", None) is None
        ],
        "totals": {
            "profesores": len(profesores),
            "preceptores": len(preceptores),
            "directivos": len(directivos),
            "padres": len(padres),
            "alumnos": len(alumnos),
            "cursos_con_alumnos": len(grouped_students),
        },
    }


def _list_staff_users(*, school, query: str = "") -> list:
    preceptor_user_ids = list(
        PreceptorCurso.objects.filter(school=school).values_list("preceptor_id", flat=True).distinct()
    )
    profesor_user_ids = list(
        ProfesorCurso.objects.filter(school=school).values_list("profesor_id", flat=True).distinct()
    )

    directivo_user_ids = list(
        SchoolMembership.objects.filter(school=school, user__groups__name="Directivos")
        .values_list("user_id", flat=True)
        .distinct()
    )
    base_filter = Q(id__in=preceptor_user_ids) | Q(id__in=profesor_user_ids) | Q(id__in=directivo_user_ids)
    qs = User.objects.exclude(is_superuser=True).filter(base_filter)

    if query:
        qs = qs.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        )
    return list(qs.order_by("first_name", "last_name", "username", "id")[:100])


def _set_staff_role_group(*, user, role: str):
    current = set(_get_user_group_names(user))
    for group_name in STAFF_ROLE_NAMES:
        if group_name == "Directivos" and role != "Directivos":
            if SchoolMembership.objects.filter(user=user).exists():
                continue
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
    if _contains_digit(first_name):
        raise ValueError("El nombre no puede contener números.")
    if _contains_digit(last_name):
        raise ValueError("El apellido no puede contener números.")
    if not username:
        raise ValueError("El nombre de usuario es obligatorio.")
    if not role:
        raise ValueError("Seleccioná un tipo de usuario válido.")
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
            {"value": "Padres", "label": "Padre, madre o tutor", "description": "Crea un acceso familiar y permite asociarlo a uno o más alumnos."},
            {"value": "Profesores", "label": "Profesor/a", "description": "Alta de docente con asignación opcional a cursos del colegio."},
            {"value": "Preceptores", "label": "Preceptor/a", "description": "Alta de preceptor con asignación opcional a cursos del colegio."},
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
