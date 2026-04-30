from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse
from functools import lru_cache

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q

from .models import Alumno, School
from .user_groups import get_user_group_names

DEFAULT_SCHOOL_LOGO_URL = "/imagenes/Logo%20Color.png"
DEFAULT_SCHOOL_PRIMARY_COLOR = "#0C1B3F"
DEFAULT_SCHOOL_ACCENT_COLOR = "#1D4ED8"
SCHOOL_RESOLUTION_CACHE_TTL = 300


def _school_resolution_cache_key(user) -> str:
    user_id = getattr(user, "id", None)
    username = str(getattr(user, "username", "") or "").strip().lower() or "anon"
    return f"school_resolution:user:{user_id or 'x'}:{username}"


@lru_cache(maxsize=64)
def _get_school_by_id_cached(school_id: int) -> Optional[School]:
    try:
        return School.objects.filter(pk=school_id).first()
    except Exception:
        return None


def _normalized_host(raw_host: str) -> str:
    value = str(raw_host or "").strip().lower()
    if not value:
        return ""
    return value.split(":", 1)[0].strip(".")


def _configured_parent_hosts() -> list[str]:
    configured = []

    try:
        for raw_host in getattr(settings, "SCHOOL_PARENT_HOSTS", []) or []:
            host = _normalized_host(raw_host)
            if host and host not in configured:
                configured.append(host)
    except Exception:
        pass

    try:
        frontend_base_url = str(getattr(settings, "FRONTEND_BASE_URL", "") or "").strip()
        if frontend_base_url:
            parsed = urlparse(frontend_base_url)
            frontend_host = _normalized_host(parsed.hostname or "")
            if frontend_host and frontend_host not in configured:
                configured.append(frontend_host)
    except Exception:
        pass

    defaults = ["localhost", "127.0.0.1"]
    for host in defaults:
        if host not in configured:
            configured.append(host)
    return configured


def get_school_by_host(raw_host: str) -> Optional[School]:
    host = _normalized_host(raw_host)
    if not host:
        return None

    for parent_host in _configured_parent_hosts():
        if host == parent_host:
            continue

        suffix = f".{parent_host}"
        if not host.endswith(suffix):
            continue

        prefix = host[: -len(suffix)].strip(".")
        if not prefix or "." in prefix or prefix == "www":
            continue

        school = get_school_by_identifier(prefix)
        if school is not None:
            return school

    return None


def get_request_host_school(request) -> Optional[School]:
    if request is None:
        return None

    host_candidates = []
    try:
        forwarded_host = request.headers.get("X-Forwarded-Host") or ""
        if forwarded_host:
            host_candidates.extend([part.strip() for part in str(forwarded_host).split(",") if part.strip()])
    except Exception:
        pass

    try:
        direct_host = request.get_host()
        if direct_host:
            host_candidates.append(direct_host)
    except Exception:
        pass

    for raw_host in host_candidates:
        school = get_school_by_host(raw_host)
        if school is not None:
            return school
    return None


def school_to_dict(school: Optional[School]) -> Optional[dict]:
    if school is None:
        return None
    return {
        "id": school.id,
        "name": school.name,
        "short_name": (getattr(school, "short_name", "") or "").strip(),
        "slug": school.slug,
        "logo_url": (getattr(school, "logo_url", "") or "").strip() or DEFAULT_SCHOOL_LOGO_URL,
        "primary_color": (getattr(school, "primary_color", "") or "").strip() or DEFAULT_SCHOOL_PRIMARY_COLOR,
        "accent_color": (getattr(school, "accent_color", "") or "").strip() or DEFAULT_SCHOOL_ACCENT_COLOR,
        "is_active": bool(school.is_active),
    }


def schools_to_dicts(schools) -> list[dict]:
    items: list[dict] = []
    seen: set[int] = set()

    for school in schools or []:
        school_id = getattr(school, "id", None)
        if school is None or school_id is None or school_id in seen:
            continue
        seen.add(school_id)
        data = school_to_dict(school)
        if data is not None:
            items.append(data)
    return items


def get_default_school() -> Optional[School]:
    try:
        active = list(School.objects.filter(is_active=True).order_by("name", "id")[:2])
        if len(active) == 1:
            return active[0]
        if active:
            return None

        schools = list(School.objects.order_by("name", "id")[:2])
        if len(schools) == 1:
            return schools[0]
    except Exception:
        return None
    return None


def get_school_by_identifier(raw_value) -> Optional[School]:
    value = str(raw_value or "").strip()
    if not value:
        return None

    try:
        if value.isdigit():
            school = School.objects.filter(pk=int(value)).first()
            if school is not None:
                return school
        school = School.objects.filter(slug__iexact=value).first()
        if school is not None:
            return school
        return School.objects.filter(name__iexact=value).first()
    except Exception:
        return None


def get_requested_school_identifier(request) -> str:
    if request is None:
        return ""

    try:
        payload = getattr(request, "data", {}) or {}
        value = payload.get("school") or payload.get("school_id") or payload.get("school_slug") or ""
        if str(value or "").strip():
            return str(value or "").strip()
    except Exception:
        pass

    try:
        value = (
            request.GET.get("school")
            or request.GET.get("school_id")
            or request.headers.get("X-School")
            or request.headers.get("X-School-Slug")
            or ""
        )
        return str(value or "").strip()
    except Exception:
        return ""


def user_can_access_school(user, school: Optional[School]) -> bool:
    if school is None:
        return False

    try:
        if user is None or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True
    except Exception:
        return False

    school_id = getattr(school, "id", None)
    if school_id is None:
        return False

    try:
        if Alumno.objects.filter(usuario=user, school_id=school_id).exists():
            return True
        if Alumno.objects.filter(padre=user, school_id=school_id).exists():
            return True
        username = str(getattr(user, "username", "") or "").strip()
        if username and Alumno.objects.filter(id_alumno__iexact=username, school_id=school_id).exists():
            return True
    except Exception:
        pass

    try:
        from .models_preceptores import PreceptorCurso, ProfesorCurso, SchoolAdmin
    except Exception:
        PreceptorCurso = None
        ProfesorCurso = None
        SchoolAdmin = None

    try:
        if SchoolAdmin is not None and SchoolAdmin.objects.filter(admin=user, school_id=school_id).exists():
            return True
        if PreceptorCurso is not None and PreceptorCurso.objects.filter(preceptor=user, school_id=school_id).exists():
            return True
        if ProfesorCurso is not None and ProfesorCurso.objects.filter(profesor=user, school_id=school_id).exists():
            return True
    except Exception:
        pass

    resolved = resolve_school_for_user(user)
    return getattr(resolved, "id", None) == school_id


def model_has_school(model_or_queryset) -> bool:
    model = getattr(model_or_queryset, "model", model_or_queryset)
    try:
        model._meta.get_field("school")
        return True
    except Exception:
        return False


def school_filter_q(school: Optional[School], field_name: str = "school", include_null: bool = False) -> Q:
    if school is None:
        return Q()

    query = Q(**{field_name: school})
    if include_null:
        query |= Q(**{f"{field_name}__isnull": True})
    return query


def scope_queryset_to_school(qs, school: Optional[School], field_name: str = "school", include_null: bool = False):
    if school is None or not model_has_school(qs):
        return qs
    return qs.filter(school_filter_q(school, field_name=field_name, include_null=include_null))


def get_unique_alumno_by_legajo(raw_value, school: Optional[School] = None) -> Optional[Alumno]:
    legajo = str(raw_value or "").strip()
    if not legajo:
        return None

    try:
        qs = scope_queryset_to_school(
            Alumno.objects.select_related("school").filter(id_alumno__iexact=legajo),
            school,
        ).order_by("id")
        if school is not None:
            return qs.first()

        matches = list(qs[:2])
        if len(matches) == 1:
            return matches[0]
    except Exception:
        return None

    return None


def resolve_school_for_user(user) -> Optional[School]:
    try:
        if user is None or not getattr(user, "is_authenticated", False):
            return None
    except Exception:
        return None

    cached_school = getattr(user, "_cached_resolved_school", None)
    if cached_school is not None or getattr(user, "_cached_resolved_school_set", False):
        return cached_school

    user_id = getattr(user, "id", None)
    cache_key = _school_resolution_cache_key(user) if user_id is not None else ""
    if cache_key:
        try:
            cached_school_id = cache.get(cache_key)
            if cached_school_id is not None:
                if cached_school_id == 0:
                    setattr(user, "_cached_resolved_school", None)
                    setattr(user, "_cached_resolved_school_set", True)
                    return None
                resolved = _get_school_by_id_cached(int(cached_school_id))
                setattr(user, "_cached_resolved_school", resolved)
                setattr(user, "_cached_resolved_school_set", True)
                return resolved
        except Exception:
            pass

    resolved_school = None
    group_names = set(get_user_group_names(user))
    has_explicit_groups = bool(group_names)

    try_alumno_link = (not has_explicit_groups) or ("Alumnos" in group_names)
    try_parent_link = (not has_explicit_groups) or ("Padres" in group_names)
    try_legajo_lookup = try_alumno_link
    try_preceptor_assignment = (not has_explicit_groups) or ("Preceptores" in group_names)
    try_profesor_assignment = (not has_explicit_groups) or ("Profesores" in group_names)
    try_school_admin_assignment = (not has_explicit_groups) or ("Administradores" in group_names)

    if try_alumno_link:
        try:
            alumno = (
                Alumno.objects.select_related("school")
                .filter(usuario=user, school__isnull=False)
                .order_by("id")
                .first()
            )
            if alumno is not None and alumno.school_id:
                resolved_school = alumno.school
        except Exception:
            pass

    if resolved_school is None and try_parent_link:
        try:
            alumno = (
                Alumno.objects.select_related("school")
                .filter(padre=user, school__isnull=False)
                .order_by("school_id", "id")
                .first()
            )
            if alumno is not None and alumno.school_id:
                resolved_school = alumno.school
        except Exception:
            pass

    if resolved_school is None and try_legajo_lookup:
        try:
            username = (getattr(user, "username", "") or "").strip()
            if username:
                alumno = get_unique_alumno_by_legajo(username)
                if alumno is not None and alumno.school_id:
                    resolved_school = alumno.school
        except Exception:
            pass

    if resolved_school is None:
        try:
            from .models_preceptores import PreceptorCurso, ProfesorCurso, SchoolAdmin
        except Exception:
            PreceptorCurso = None
            ProfesorCurso = None
            SchoolAdmin = None

        if try_school_admin_assignment and SchoolAdmin is not None:
            try:
                assignment = (
                    SchoolAdmin.objects.select_related("school")
                    .filter(admin=user, school__isnull=False)
                    .order_by("school_id", "id")
                    .first()
                )
                if assignment is not None and assignment.school_id:
                    resolved_school = assignment.school
            except Exception:
                pass

        if resolved_school is None and try_preceptor_assignment and PreceptorCurso is not None:
            try:
                asignacion = (
                    PreceptorCurso.objects.select_related("school")
                    .filter(preceptor=user, school__isnull=False)
                    .order_by("school_id", "id")
                    .first()
                )
                if asignacion is not None and asignacion.school_id:
                    resolved_school = asignacion.school
            except Exception:
                pass

        if resolved_school is None and try_profesor_assignment and ProfesorCurso is not None:
            try:
                asignacion = (
                    ProfesorCurso.objects.select_related("school")
                    .filter(profesor=user, school__isnull=False)
                    .order_by("school_id", "id")
                    .first()
                )
                if asignacion is not None and asignacion.school_id:
                    resolved_school = asignacion.school
            except Exception:
                pass

    if resolved_school is None:
        resolved_school = get_default_school()

    if cache_key:
        try:
            cache.set(cache_key, getattr(resolved_school, "id", 0) or 0, SCHOOL_RESOLUTION_CACHE_TTL)
        except Exception:
            pass

    try:
        setattr(user, "_cached_resolved_school", resolved_school)
        setattr(user, "_cached_resolved_school_set", True)
    except Exception:
        pass

    return resolved_school


def get_available_schools_for_user(user, *, active_school: Optional[School] = None) -> list[School]:
    try:
        if getattr(user, "is_authenticated", False) and getattr(user, "is_superuser", False):
            schools = list(School.objects.filter(is_active=True).order_by("name", "id"))
            if active_school is not None and all(getattr(s, "id", None) != active_school.id for s in schools):
                schools.insert(0, active_school)
            return schools
    except Exception:
        pass

    school = active_school or resolve_school_for_user(user)
    return [school] if school is not None else []


def get_available_school_dicts_for_user(user, *, active_school: Optional[School] = None) -> list[dict]:
    return schools_to_dicts(get_available_schools_for_user(user, active_school=active_school))


def get_request_school(request) -> Optional[School]:
    if request is None:
        return None

    if getattr(request, "_cached_active_school_resolved", False):
        return getattr(request, "_cached_active_school", None)

    user = getattr(request, "user", None)
    host_school = get_request_host_school(request)

    raw_value = get_requested_school_identifier(request)

    if raw_value:
        school = get_school_by_identifier(raw_value)
        if school is not None and (
            getattr(user, "is_superuser", False) or user_can_access_school(user, school)
        ):
            request._cached_active_school = school
            request._cached_active_school_resolved = True
            return school

    try:
        if getattr(user, "is_superuser", False):
            request._cached_active_school = host_school
            request._cached_active_school_resolved = True
            return host_school
    except Exception:
        pass

    try:
        if user is None or not getattr(user, "is_authenticated", False):
            school = host_school or get_default_school()
            request._cached_active_school = school
            request._cached_active_school_resolved = True
            return school
    except Exception:
        school = host_school or get_default_school()
        request._cached_active_school = school
        request._cached_active_school_resolved = True
        return school

    school = resolve_school_for_user(user)
    request._cached_active_school = school
    request._cached_active_school_resolved = True
    return school
