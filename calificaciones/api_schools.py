from concurrent.futures import ThreadPoolExecutor

from django.db import close_old_connections, transaction
from django.db.utils import OperationalError, ProgrammingError
from django.db.models import Count, Exists, OuterRef, Q
from django.utils import timezone
from django.utils.text import slugify
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .forms import SchoolAdminForm
from .models import (
    AlertaAcademica,
    AlertaInasistencia,
    Alumno,
    Asistencia,
    Comunicado,
    Evento,
    Mensaje,
    Nota,
    Notificacion,
    Sancion,
    School,
    SchoolCourse,
    SchoolDeletionJob,
)
from .models_preceptores import PreceptorCurso, ProfesorCurso, SchoolAdmin, SchoolMembership
from .schools import (
    get_available_school_dicts_for_user,
    get_default_school,
    get_requested_school_identifier,
    get_request_school,
    get_school_by_identifier,
    get_request_host_school,
    school_to_dict,
    schools_to_dicts,
)
from .utils_cursos import clear_school_course_cache, get_school_course_choices
from .user_groups import get_user_group_names

User = get_user_model()
_SCHOOL_DELETION_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="school-delete")


def _school_deletion_jobs_ready() -> bool:
    try:
        list(SchoolDeletionJob.objects.order_by("-id").values_list("id", flat=True)[:1])
        return True
    except (OperationalError, ProgrammingError):
        return False


def _require_platform_admin(user):
    return bool(getattr(user, "is_authenticated", False) and getattr(user, "is_superuser", False))


def _is_school_admin(user) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    groups = set(get_user_group_names(user))
    if not groups.intersection({"Administradores", "Administrador"}):
        return False
    try:
        from .models_preceptores import SchoolAdmin
    except Exception:
        return False
    try:
        return SchoolAdmin.objects.filter(admin=user).exists()
    except Exception:
        return False


def _require_school_course_admin(user):
    return bool(getattr(user, "is_authenticated", False) and _is_school_admin(user))


def _user_can_manage_school_courses(user, school: School | None) -> bool:
    if school is None:
        return False
    if getattr(user, "is_superuser", False):
        return True
    try:
        return SchoolAdmin.objects.filter(admin=user, school=school).exists()
    except Exception:
        return False


def _resolve_course_admin_scope(request):
    if not _require_school_course_admin(getattr(request, "user", None)):
        return None, Response({"detail": "No autorizado."}, status=403)

    active_school = get_request_school(request)
    if active_school is None and getattr(request.user, "is_superuser", False):
        active_school = (
            School.objects.filter(is_active=True).order_by("name", "id").first()
            or School.objects.order_by("name", "id").first()
        )
    if active_school is None:
        return None, Response({"detail": "No hay un colegio activo seleccionado."}, status=400)

    if not _user_can_manage_school_courses(request.user, active_school):
        return None, Response({"detail": "No autorizado para el colegio activo."}, status=403)

    return active_school, None


def _admin_school_to_dict(school: School) -> dict:
    data = school_to_dict(school) or {}
    data.update(
        {
            "created_at": school.created_at.isoformat() if getattr(school, "created_at", None) else None,
            "updated_at": school.updated_at.isoformat() if getattr(school, "updated_at", None) else None,
            "courses_count": int(getattr(school, "courses_count", 0) or 0),
            "students_count": int(getattr(school, "students_count", 0) or 0),
        }
    )
    return data


def _admin_user_to_dict(user) -> dict:
    groups = list(user.groups.order_by("name").values_list("name", flat=True))
    full_name = " ".join(
        part
        for part in [
            str(getattr(user, "first_name", "") or "").strip(),
            str(getattr(user, "last_name", "") or "").strip(),
        ]
        if part
    ).strip()
    return {
        "id": user.id,
        "username": str(getattr(user, "username", "") or "").strip(),
        "full_name": full_name,
        "email": str(getattr(user, "email", "") or "").strip(),
        "is_active": bool(getattr(user, "is_active", True)),
        "groups": groups,
    }


def _school_admins_to_dict(school: School) -> dict:
    data = _admin_school_to_dict(school)
    assignments = list(
        SchoolAdmin.objects.select_related("admin")
        .filter(school=school)
        .order_by("admin__first_name", "admin__last_name", "admin__username", "id")
    )
    admins = [_admin_user_to_dict(assignment.admin) for assignment in assignments]
    data.update(
        {
            "admins": admins,
            "admins_count": len(admins),
        }
    )
    return data


def _normalize_admin_ids(raw_value) -> list[int]:
    if not isinstance(raw_value, list):
        return []
    normalized = []
    seen = set()
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


def _admin_course_to_dict(course: SchoolCourse) -> dict:
    return {
        "id": course.id,
        "school_id": course.school_id,
        "code": str(getattr(course, "code", "") or "").strip(),
        "name": str(getattr(course, "name", "") or "").strip(),
        "is_active": bool(getattr(course, "is_active", True)),
        "sort_order": int(getattr(course, "sort_order", 0) or 0),
        "students_count": int(getattr(course, "students_count", 0) or 0),
    }


def _attach_school_course_student_counts(school: School, courses: list[SchoolCourse]) -> list[SchoolCourse]:
    course_ids = {
        int(getattr(course, "id", 0) or 0): course
        for course in (courses or [])
        if getattr(course, "id", None) is not None
    }
    course_ids.pop(0, None)
    codes_to_course_ids: dict[str, list[int]] = {}
    for course in courses or []:
        code = str(getattr(course, "code", "") or "").strip().upper()
        if not code:
            continue
        codes_to_course_ids.setdefault(code, []).append(course.id)
        course.students_count = 0

    student_ids_by_course: dict[int, set[int]] = {course.id: set() for course in courses or []}
    student_rows = Alumno.objects.filter(school=school).values("id", "school_course_id", "curso")
    for row in student_rows:
        alumno_id = int(row.get("id") or 0)
        if alumno_id <= 0:
            continue

        school_course_id = int(row.get("school_course_id") or 0)
        if school_course_id in student_ids_by_course:
            student_ids_by_course[school_course_id].add(alumno_id)
            continue

        course_code = str(row.get("curso") or "").strip().upper()
        if not course_code:
            continue
        for course_id in codes_to_course_ids.get(course_code, []):
            student_ids_by_course[course_id].add(alumno_id)

    for course in courses or []:
        course.students_count = len(student_ids_by_course.get(course.id, set()))
    return courses


def _school_courses_to_dict(school: School) -> dict:
    data = _admin_school_to_dict(school)
    courses = list(SchoolCourse.objects.filter(school=school).order_by("sort_order", "name", "id"))
    courses = _attach_school_course_student_counts(school, courses)
    data.update(
        {
            "courses": [_admin_course_to_dict(course) for course in courses],
            "courses_count": len(courses),
        }
    )
    return data


def _school_with_courses_to_dict(school: School) -> dict:
    school.courses_count = int(getattr(school, "courses_count", 0) or 0)
    school.students_count = int(getattr(school, "students_count", 0) or 0)
    data = _admin_school_to_dict(school)
    prefetched_courses = getattr(school, "_prefetched_admin_courses", None)
    if prefetched_courses is None:
        return _school_courses_to_dict(school)
    data.update(
        {
            "courses": [_admin_course_to_dict(course) for course in prefetched_courses],
            "courses_count": len(prefetched_courses),
        }
    )
    return data


def _course_payload_from_request(request, *, instance: SchoolCourse | None = None) -> dict:
    raw = request.data.copy() if hasattr(request.data, "copy") else dict(request.data or {})
    if hasattr(raw, "dict"):
        raw = raw.dict()
    elif not isinstance(raw, dict):
        raw = dict(raw or {})

    payload = {}
    for field in ("code", "name", "sort_order", "is_active"):
        if field in raw:
            payload[field] = raw.get(field)

    if instance is not None:
        for field in ("code", "name", "sort_order", "is_active"):
            payload.setdefault(field, getattr(instance, field))

    payload["code"] = str(payload.get("code") or "").strip().upper()[:20]
    payload["name"] = str(payload.get("name") or "").strip()[:120]
    if not payload["name"]:
        payload["name"] = payload["code"]
    try:
        payload["sort_order"] = int(payload.get("sort_order") or 0)
    except (TypeError, ValueError):
        payload["sort_order"] = 0
    if payload["sort_order"] < 0:
        payload["sort_order"] = 0
    value = payload.get("is_active", True)
    if isinstance(value, str):
        payload["is_active"] = value.strip().lower() in {"1", "true", "yes", "on", "si", "sí"}
    else:
        payload["is_active"] = bool(value)
    return payload


def _school_payload_from_request(request, *, instance: School | None = None) -> dict:
    raw = request.data.copy() if hasattr(request.data, "copy") else dict(request.data or {})
    if hasattr(raw, "dict"):
        raw = raw.dict()
    elif not isinstance(raw, dict):
        raw = dict(raw or {})

    allowed = {
        "name",
        "short_name",
        "slug",
        "logo_url",
        "primary_color",
        "accent_color",
        "is_active",
    }

    if instance is not None:
        payload = {field: getattr(instance, field) for field in allowed}
        payload.update({key: value for key, value in raw.items() if key in allowed})
    else:
        payload = {key: value for key, value in raw.items() if key in allowed}

    if "slug" in payload:
        payload["slug"] = slugify(str(payload.get("slug") or "").strip())[:80]
    for field in ("name", "short_name", "logo_url", "primary_color", "accent_color"):
        if field in payload:
            payload[field] = str(payload.get(field) or "").strip()
    if "is_active" in payload:
        value = payload.get("is_active")
        if isinstance(value, str):
            payload["is_active"] = value.strip().lower() in {"1", "true", "yes", "on", "si", "sí"}
        else:
            payload["is_active"] = bool(value)
    return payload


@api_view(["GET"])
@permission_classes([AllowAny])
def public_school_branding(request):
    raw_school = (
        request.GET.get("school")
        or request.GET.get("school_id")
        or request.headers.get("X-School")
        or request.headers.get("X-School-Slug")
        or ""
    ).strip()

    school = get_school_by_identifier(raw_school) if raw_school else get_request_host_school(request) or get_default_school()
    if school is None:
        if raw_school:
            return Response({"detail": "Colegio no encontrado."}, status=404)
        return Response({"school": None}, status=200)

    return Response({"school": school_to_dict(school)}, status=200)


@api_view(["GET"])
@permission_classes([AllowAny])
def public_school_directory(request):
    query = str(request.GET.get("q") or "").strip()

    schools_qs = School.objects.filter(is_active=True).order_by("name", "id")
    if query:
        schools_qs = schools_qs.filter(
            Q(name__icontains=query)
            | Q(short_name__icontains=query)
            | Q(slug__icontains=query)
        )

    schools = list(schools_qs.distinct().order_by("name", "id"))
    return Response({"schools": schools_to_dicts(schools)}, status=200)


def _generate_school_slug(*, name: str, requested_slug: str = "") -> str:
    raw_slug = str(requested_slug or "").strip()
    if raw_slug:
        normalized = slugify(raw_slug)[:80]
        return normalized or (slugify(name)[:80] or "colegio")

    base_slug = slugify(name)[:80] or "colegio"
    candidate = base_slug
    suffix = 2
    while School.objects.filter(slug__iexact=candidate).exists():
        suffix_token = f"-{suffix}"
        candidate = f"{base_slug[: max(1, 80 - len(suffix_token))]}{suffix_token}"
        suffix += 1
    return candidate


def _seed_school_courses(school) -> int:
    course_rows = get_school_course_choices(school=None, fallback_to_defaults=True)
    pending = []
    for index, (course_code, course_name) in enumerate(course_rows, start=1):
        pending.append(
            SchoolCourse(
                school=school,
                code=str(course_code).strip().upper(),
                name=str(course_name).strip() or str(course_code).strip().upper(),
                sort_order=index,
                is_active=True,
            )
        )
    SchoolCourse.objects.bulk_create(pending)
    return len(pending)


def _delete_school_tree(school: School) -> None:
    with transaction.atomic():
        clear_school_course_cache(school)

        SchoolAdmin.objects.filter(school=school).delete()
        SchoolMembership.objects.filter(school=school).delete()
        PreceptorCurso.objects.filter(school=school).delete()
        ProfesorCurso.objects.filter(school=school).delete()

        Notificacion.objects.filter(school=school).delete()
        AlertaAcademica.objects.filter(school=school).delete()
        AlertaInasistencia.objects.filter(school=school).delete()
        Asistencia.objects.filter(school=school).delete()
        Sancion.objects.filter(school=school).delete()
        Nota.objects.filter(school=school).delete()
        Evento.objects.filter(school=school).delete()
        Comunicado.objects.filter(school=school).delete()
        Mensaje.objects.filter(school=school).delete()

        Alumno.objects.filter(school=school).delete()
        SchoolCourse.objects.filter(school=school).delete()
        school.delete()


def _school_deletion_job_to_dict(job: SchoolDeletionJob) -> dict:
    return {
        "id": job.id,
        "school_id": job.school_id,
        "school_name": str(getattr(job, "school_name", "") or "").strip(),
        "school_slug": str(getattr(job, "school_slug", "") or "").strip(),
        "status": str(getattr(job, "status", "") or "").strip(),
        "error": str(getattr(job, "error", "") or "").strip(),
        "requested_at": job.requested_at.isoformat() if getattr(job, "requested_at", None) else None,
        "started_at": job.started_at.isoformat() if getattr(job, "started_at", None) else None,
        "finished_at": job.finished_at.isoformat() if getattr(job, "finished_at", None) else None,
    }


def _run_school_deletion_job(job_id: int) -> None:
    close_old_connections()
    now = timezone.now()
    started = SchoolDeletionJob.objects.filter(
        pk=job_id,
        status=SchoolDeletionJob.STATUS_PENDING,
    ).update(
        status=SchoolDeletionJob.STATUS_RUNNING,
        started_at=now,
        finished_at=None,
        error="",
    )
    if not started:
        close_old_connections()
        return

    try:
        job = SchoolDeletionJob.objects.select_related("school").get(pk=job_id)
        school = getattr(job, "school", None)
        if school is not None:
            _delete_school_tree(school)
        SchoolDeletionJob.objects.filter(pk=job_id).update(
            status=SchoolDeletionJob.STATUS_COMPLETED,
            finished_at=timezone.now(),
            error="",
            school=None,
        )
    except Exception as exc:
        SchoolDeletionJob.objects.filter(pk=job_id).update(
            status=SchoolDeletionJob.STATUS_FAILED,
            finished_at=timezone.now(),
            error=str(exc)[:4000],
        )
    finally:
        close_old_connections()


def _schedule_school_deletion_job(job_id: int) -> None:
    _SCHOOL_DELETION_EXECUTOR.submit(_run_school_deletion_job, job_id)


def _schedule_pending_school_deletion_jobs(limit: int = 3) -> None:
    if not _school_deletion_jobs_ready():
        return
    pending_ids = list(
        SchoolDeletionJob.objects.filter(status=SchoolDeletionJob.STATUS_PENDING)
        .order_by("requested_at", "id")
        .values_list("id", flat=True)[: max(1, int(limit or 1))]
    )
    for job_id in pending_ids:
        _schedule_school_deletion_job(int(job_id))


def _enqueue_school_deletion_job(*, school: School, requested_by) -> tuple[SchoolDeletionJob, bool]:
    if not _school_deletion_jobs_ready():
        raise RuntimeError("Falta aplicar la migracion de SchoolDeletionJob.")
    active_statuses = [
        SchoolDeletionJob.STATUS_PENDING,
        SchoolDeletionJob.STATUS_RUNNING,
    ]
    existing = (
        SchoolDeletionJob.objects.filter(school=school, status__in=active_statuses)
        .order_by("-requested_at", "-id")
        .first()
    )
    if existing is not None:
        return existing, False

    if school.is_active:
        school.is_active = False
        school.save(update_fields=["is_active", "updated_at"])

    job = SchoolDeletionJob.objects.create(
        school=school,
        requested_by=requested_by,
        school_name=str(getattr(school, "name", "") or "").strip(),
        school_slug=str(getattr(school, "slug", "") or "").strip(),
        status=SchoolDeletionJob.STATUS_PENDING,
    )
    transaction.on_commit(lambda: _schedule_school_deletion_job(job.id))
    return job, True


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def admin_create_school(request):
    if not _require_platform_admin(request.user):
        return Response({"detail": "No autorizado."}, status=403)

    if request.method == "GET":
        jobs_ready = _school_deletion_jobs_ready()
        if jobs_ready:
            _schedule_pending_school_deletion_jobs()
            active_deletion_jobs = SchoolDeletionJob.objects.filter(
                school_id=OuterRef("pk"),
                status__in=[
                    SchoolDeletionJob.STATUS_PENDING,
                    SchoolDeletionJob.STATUS_RUNNING,
                ],
            )
            schools_qs = (
                School.objects.annotate(
                    courses_count=Count("courses", distinct=True),
                    students_count=Count("alumnos", distinct=True),
                    deletion_in_progress=Exists(active_deletion_jobs),
                )
                .filter(deletion_in_progress=False)
                .order_by("name", "id")
            )
        else:
            schools_qs = School.objects.annotate(
                courses_count=Count("courses", distinct=True),
                students_count=Count("alumnos", distinct=True),
            ).order_by("name", "id")
        query = str(request.GET.get("q") or "").strip()
        if query:
            schools_qs = schools_qs.filter(
                Q(name__icontains=query)
                | Q(short_name__icontains=query)
                | Q(slug__icontains=query)
            )
        schools = [_admin_school_to_dict(school) for school in schools_qs]
        return Response({"schools": schools}, status=200)

    payload = _school_payload_from_request(request)

    name = str(payload.get("name") or "").strip()
    requested_slug = str(payload.get("slug") or "").strip()
    payload["slug"] = _generate_school_slug(name=name, requested_slug=requested_slug)
    payload["is_active"] = bool(payload.get("is_active", True))

    form = SchoolAdminForm(data=payload)
    if not form.is_valid():
        return Response({"errors": form.errors}, status=400)

    with transaction.atomic():
        school = form.save()
        seeded_courses = _seed_school_courses(school)

    return Response(
        {
            "school": school_to_dict(school),
            "available_schools": get_available_school_dicts_for_user(request.user, active_school=school),
            "seeded_courses": seeded_courses,
        },
        status=201,
    )


@api_view(["PATCH", "PUT", "DELETE"])
@permission_classes([IsAuthenticated])
def admin_update_school(request, school_id: int):
    if not _require_platform_admin(request.user):
        return Response({"detail": "No autorizado."}, status=403)

    school = School.objects.filter(pk=school_id).first()
    if school is None:
        return Response({"detail": "Colegio no encontrado."}, status=404)

    if request.method == "DELETE":
        try:
            with transaction.atomic():
                job, created = _enqueue_school_deletion_job(school=school, requested_by=request.user)
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=503)
        next_active_school = (
            School.objects.filter(is_active=True).exclude(pk=school_id).order_by("name", "id").first()
            or School.objects.exclude(pk=school_id).order_by("name", "id").first()
        )
        return Response(
            {
                "deleted_id": school_id,
                "detail": "Borrado iniciado." if created else "El borrado ya estaba en progreso.",
                "job": _school_deletion_job_to_dict(job),
                "available_schools": get_available_school_dicts_for_user(
                    request.user,
                    active_school=next_active_school,
                ),
            },
            status=202,
        )

    payload = _school_payload_from_request(request, instance=school)
    if not payload.get("slug"):
        payload["slug"] = _generate_school_slug(name=payload.get("name") or school.name)

    form = SchoolAdminForm(data=payload, instance=school)
    if not form.is_valid():
        return Response({"errors": form.errors}, status=400)

    updated = form.save()
    updated.courses_count = updated.courses.count()
    updated.students_count = updated.alumnos.count()
    return Response(
        {
            "school": _admin_school_to_dict(updated),
            "available_schools": get_available_school_dicts_for_user(request.user, active_school=updated),
        },
        status=200,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_school_deletion_job(request, job_id: int):
    if not _require_platform_admin(request.user):
        return Response({"detail": "No autorizado."}, status=403)

    job = SchoolDeletionJob.objects.filter(pk=job_id).first()
    if job is None:
        return Response({"detail": "Trabajo de borrado no encontrado."}, status=404)

    return Response({"job": _school_deletion_job_to_dict(job)}, status=200)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_school_admins(request):
    if not _require_platform_admin(request.user):
        return Response({"detail": "No autorizado."}, status=403)

    query = str(request.GET.get("q") or "").strip()
    schools_qs = School.objects.annotate(
        courses_count=Count("courses", distinct=True),
        students_count=Count("alumnos", distinct=True),
    ).order_by("name", "id")
    if query:
        schools_qs = schools_qs.filter(
            Q(name__icontains=query)
            | Q(short_name__icontains=query)
            | Q(slug__icontains=query)
        )

    user_query = str(request.GET.get("user_q") or "").strip()
    candidates_qs = User.objects.exclude(is_superuser=True).order_by("first_name", "last_name", "username", "id")
    if user_query:
        candidates_qs = candidates_qs.filter(
            Q(username__icontains=user_query)
            | Q(first_name__icontains=user_query)
            | Q(last_name__icontains=user_query)
            | Q(email__icontains=user_query)
        )
    else:
        candidates_qs = candidates_qs.filter(
            Q(groups__name__in=["Administradores", "Administrador"])
            | Q(school_admin_assignments__isnull=False)
        )

    return Response(
        {
            "schools": [_school_admins_to_dict(school) for school in schools_qs.distinct()],
            "users": [_admin_user_to_dict(user) for user in candidates_qs.distinct()[:200]],
        },
        status=200,
    )


@api_view(["PATCH", "PUT"])
@permission_classes([IsAuthenticated])
def admin_update_school_admins(request, school_id: int):
    if not _require_platform_admin(request.user):
        return Response({"detail": "No autorizado."}, status=403)

    school = School.objects.filter(pk=school_id).first()
    if school is None:
        return Response({"detail": "Colegio no encontrado."}, status=404)

    admin_ids = _normalize_admin_ids((request.data or {}).get("admin_ids"))
    admins = list(User.objects.filter(id__in=admin_ids).exclude(is_superuser=True).order_by("id"))
    if len(admins) != len(admin_ids):
        return Response({"detail": "Uno o más usuarios no existen o no son asignables."}, status=400)

    desired_ids = {user.id for user in admins}
    with transaction.atomic():
        admin_group, _ = Group.objects.get_or_create(name="Administradores")
        for user in admins:
            user.groups.add(admin_group)

        SchoolAdmin.objects.filter(school=school).exclude(admin_id__in=desired_ids).delete()
        existing_ids = set(SchoolAdmin.objects.filter(school=school).values_list("admin_id", flat=True))
        pending = [
            SchoolAdmin(school=school, admin=user)
            for user in admins
            if user.id not in existing_ids
        ]
        if pending:
            SchoolAdmin.objects.bulk_create(pending)

    school.courses_count = school.courses.count()
    school.students_count = school.alumnos.count()
    return Response({"school": _school_admins_to_dict(school)}, status=200)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_school_courses(request):
    active_school, denied = _resolve_course_admin_scope(request)
    if denied is not None:
        return denied

    requested_school_identifier = get_requested_school_identifier(request)
    should_scope_to_active_school = (
        not getattr(request.user, "is_superuser", False)
        or bool(str(requested_school_identifier or "").strip())
    )

    if should_scope_to_active_school:
        school = (
            School.objects.filter(pk=getattr(active_school, "id", None))
            .annotate(
                courses_count=Count("courses", distinct=True),
                students_count=Count("alumnos", distinct=True),
            )
            .first()
        )
        if school is None:
            return Response({"detail": "Colegio no encontrado."}, status=404)

        school._prefetched_admin_courses = _attach_school_course_student_counts(
            school,
            list(
                SchoolCourse.objects.filter(school=school)
                .order_by("sort_order", "name", "id")
            ),
        )
        return Response({"schools": [_school_with_courses_to_dict(school)]}, status=200)

    query = str(request.GET.get("q") or "").strip()
    schools_qs = School.objects.annotate(
        courses_count=Count("courses", distinct=True),
        students_count=Count("alumnos", distinct=True),
    ).order_by("name", "id")

    if query:
        schools_qs = schools_qs.filter(
            Q(name__icontains=query)
            | Q(short_name__icontains=query)
            | Q(slug__icontains=query)
        )

    return Response(
        {
            "schools": [_school_courses_to_dict(school) for school in schools_qs.distinct()],
        },
        status=200,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def admin_create_school_course(request, school_id: int):
    active_school, denied = _resolve_course_admin_scope(request)
    if denied is not None:
        return denied

    school = School.objects.filter(pk=school_id).first()
    if school is None:
        return Response({"detail": "Colegio no encontrado."}, status=404)
    if not getattr(request.user, "is_superuser", False) and getattr(active_school, "id", None) != school.id:
        return Response({"detail": "Solo podés crear cursos en el colegio activo."}, status=403)

    payload = _course_payload_from_request(request)
    if not payload["code"]:
        return Response({"detail": "El codigo del curso es obligatorio."}, status=400)
    if SchoolCourse.objects.filter(school=school, code__iexact=payload["code"]).exists():
        return Response({"detail": "Ya existe un curso con ese codigo en este colegio."}, status=400)

    course = SchoolCourse.objects.create(school=school, **payload)
    clear_school_course_cache(school)
    school.courses_count = school.courses.count()
    school.students_count = school.alumnos.count()
    return Response(
        {
            "course": _admin_course_to_dict(course),
            "school": _school_courses_to_dict(school),
        },
        status=201,
    )


@api_view(["PATCH", "PUT"])
@permission_classes([IsAuthenticated])
def admin_update_school_course(request, course_id: int):
    active_school, denied = _resolve_course_admin_scope(request)
    if denied is not None:
        return denied

    course = SchoolCourse.objects.select_related("school").filter(pk=course_id).first()
    if course is None:
        return Response({"detail": "Curso no encontrado."}, status=404)
    if not getattr(request.user, "is_superuser", False) and getattr(active_school, "id", None) != getattr(course.school, "id", None):
        return Response({"detail": "Solo podés editar cursos del colegio activo."}, status=403)

    payload = _course_payload_from_request(request, instance=course)
    if not payload["code"]:
        return Response({"detail": "El codigo del curso es obligatorio."}, status=400)
    if (
        SchoolCourse.objects.filter(school=course.school, code__iexact=payload["code"])
        .exclude(pk=course.pk)
        .exists()
    ):
        return Response({"detail": "Ya existe otro curso con ese codigo en este colegio."}, status=400)

    for field, value in payload.items():
        setattr(course, field, value)
    course.save(update_fields=["code", "name", "sort_order", "is_active", "updated_at"])
    clear_school_course_cache(course.school)
    course.students_count = course.alumnos.count()
    return Response(
        {
            "course": _admin_course_to_dict(course),
            "school": _school_courses_to_dict(course.school),
        },
        status=200,
    )
