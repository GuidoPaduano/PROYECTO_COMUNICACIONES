from django.conf import settings
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Q
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils.text import get_valid_filename, slugify
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from ..forms import SchoolAdminForm
from ..models import School, SchoolCourse, SchoolDeletionJob
from ..models_preceptores import SchoolAdmin
from ..schools import (
    get_available_school_dicts_for_user,
    get_requested_school_identifier,
    get_school_by_identifier,
    get_request_host_school,
    get_default_school,
    school_to_dict,
    schools_to_dicts,
)
from ..utils_cursos import clear_school_course_cache

from ._helpers import (
    _admin_course_to_dict,
    _admin_school_to_dict,
    _admin_user_to_dict,
    _attach_school_course_student_counts,
    _course_payload_from_request,
    _enqueue_school_deletion_job,
    _generate_school_slug,
    _normalize_admin_ids,
    _require_platform_admin,
    _resolve_course_admin_scope,
    _schedule_pending_school_deletion_jobs,
    _school_admins_to_dict,
    _school_courses_to_dict,
    _school_deletion_job_to_dict,
    _school_deletion_jobs_ready,
    _school_payload_from_request,
    _school_with_courses_to_dict,
    _seed_school_courses,
    _SCHOOL_LOGO_ALLOWED_EXTENSIONS,
    _SCHOOL_LOGO_MAX_BYTES,
)

User = get_user_model()


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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def admin_upload_school_logo(request, school_id: int):
    if not _require_platform_admin(request.user):
        return Response({"detail": "No autorizado."}, status=403)

    school = School.objects.filter(pk=school_id).first()
    if school is None:
        return Response({"detail": "Colegio no encontrado."}, status=404)

    logo = request.FILES.get("logo")
    if logo is None:
        return Response({"detail": "Selecciona un archivo de logo."}, status=400)

    if getattr(logo, "size", 0) > _SCHOOL_LOGO_MAX_BYTES:
        return Response({"detail": "El logo no puede superar 2 MB."}, status=400)

    original_name = get_valid_filename(getattr(logo, "name", "") or "logo")
    extension = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    content_type = str(getattr(logo, "content_type", "") or "").lower()
    if extension not in _SCHOOL_LOGO_ALLOWED_EXTENSIONS or not content_type.startswith("image/"):
        return Response({"detail": "El logo debe ser una imagen PNG, JPG, WEBP o GIF."}, status=400)

    filename = f"{slugify(school.slug or school.name) or school.id}-logo.{extension}"
    path = default_storage.save(f"school-logos/{filename}", logo)
    logo_url = f"{settings.MEDIA_URL.rstrip('/')}/{path}".replace("\\", "/")

    school.logo_url = logo_url
    school.save(update_fields=["logo_url", "updated_at"])
    school.courses_count = school.courses.count()
    school.students_count = school.alumnos.count()

    return Response(
        {
            "school": _admin_school_to_dict(school),
            "available_schools": get_available_school_dicts_for_user(request.user, active_school=school),
            "logo_url": logo_url,
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
