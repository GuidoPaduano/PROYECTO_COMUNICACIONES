from django.db import transaction
from django.db.models import Q
from django.utils.text import slugify
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .forms import SchoolAdminForm
from .models import School, SchoolCourse
from .schools import (
    get_available_school_dicts_for_user,
    get_default_school,
    get_school_by_identifier,
    get_request_host_school,
    school_to_dict,
    schools_to_dicts,
)
from .utils_cursos import get_school_course_choices


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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def admin_create_school(request):
    if not getattr(request.user, "is_superuser", False):
        return Response({"detail": "No autorizado."}, status=403)

    payload = request.data.copy() if hasattr(request.data, "copy") else dict(request.data or {})
    if hasattr(payload, "dict"):
        payload = payload.dict()
    elif not isinstance(payload, dict):
        payload = dict(payload or {})

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
