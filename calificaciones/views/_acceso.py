# calificaciones/views/_acceso.py
# Helper: Vista previa de rol, formularios, helpers de acceso, roles, cursos y mensajes

import json
import logging
from functools import lru_cache

from django.core.cache import cache
from django.db.models import Count, Q

from rest_framework.decorators import (
    api_view, authentication_classes, permission_classes, parser_classes, throttle_classes
)

from ..course_access import (
    CourseRef,
    course_ref_matches,
    filter_course_options_by_refs,
    get_assignment_course_refs,
    normalize_course_code,
)
from ..forms import EventoForm as BaseEventoForm
from ..models import Alumno, Mensaje, SchoolCourse
from ..schools import (
    get_request_school,
    scope_queryset_to_school,
)
from ..user_groups import get_user_group_names
from ..utils_cursos import (
    get_course_label,
    get_school_course_by_id,
    get_school_course_dicts,
    resolve_course_reference,
)
from ..models import resolve_school_course_for_value

logger = logging.getLogger(__name__)
ASSIGNMENT_REFS_CACHE_TTL = 120

try:
    # ✅ NUEVO: si existen los modelos reales preceptor/profesor→cursos, los usamos para permisos
    from ..models_preceptores import PreceptorCurso, ProfesorCurso  # type: ignore
except Exception:
    PreceptorCurso = None
    ProfesorCurso = None


# ============================================================
# Helper: Vista previa de rol ("Vista como…") para superusuario
# ============================================================
def _get_preview_role(request):
    """
    Devuelve un rol de vista previa si el usuario es superusuario y pidió simular un rol.
    Lee `view_as` (querystring) o el header `X-Preview-Role`.
    Valores válidos: 'Profesores', 'Preceptores', 'Directivos', 'Padres', 'Alumnos'.
    """
    try:
        role = (request.GET.get("view_as") or request.headers.get("X-Preview-Role") or "").strip()
    except Exception:
        role = ""
    valid = {"Profesores", "Preceptores", "Directivos", "Padres", "Alumnos"}
    if role in valid and getattr(request.user, "is_superuser", False):
        return role
    return None


# =========================================================
#  Formularios
# =========================================================
class EventoForm(BaseEventoForm):
    pass


# =========================================================
#  Helpers
# =========================================================
def _coerce_json(request):
    """Intenta parsear JSON manualmente si request.data viene vacío."""
    if getattr(request, "data", None):
        return request.data
    try:
        raw = (request.body or b"").decode("utf-8")
        return json.loads(raw) if raw else {}
    except Exception:
        return {}

def _rol_principal(user):
    if getattr(user, "is_superuser", False):
        return "superusuario"
    group_names = set(get_user_group_names(user))
    for g in ("Administradores", "Directivos", "Profesores", "Padres", "Alumnos", "Preceptores"):
        if g in group_names:
            return g
    return "—"


def _alumno_to_dict(a: Alumno):
    if not a:
        return None
    school_course = getattr(a, "school_course", None)
    return {
        "id": a.id,
        "id_alumno": getattr(a, "id_alumno", None),
        "nombre": a.nombre,
        "apellido": getattr(a, "apellido", None),
        "school_course_id": getattr(a, "school_course_id", None),
        "school_course_name": getattr(school_course, "name", None) or getattr(school_course, "code", None) or getattr(a, "curso", None),
        "padre_id": a.padre_id,
        "usuario_id": getattr(a, "usuario_id", None),
    }


# ===== Helpers de rol efectivos (aplican vista previa) =====
def _effective_groups(request):
    cached = getattr(request, "_cached_effective_groups", None)
    if cached is not None:
        return cached
    pr = _get_preview_role(request)
    if pr and getattr(request.user, "is_superuser", False):
        groups = [pr]
        setattr(request, "_cached_effective_groups", groups)
        return groups
    try:
        groups = list(get_user_group_names(request.user))
    except Exception:
        groups = []
    setattr(request, "_cached_effective_groups", groups)
    return groups


def _has_role(request, *roles):
    eff = set(_effective_groups(request))
    return any(r in eff for r in roles)


# ===== Helper: detectar si un campo existe en el modelo (para contadores) =====
@lru_cache(maxsize=None)
def _has_model_field(model, name: str) -> bool:
    try:
        model._meta.get_field(name)
        return True
    except Exception:
        return False


# =========================================================
#  ✅ NUEVO: permisos de PRECEPTOR por curso (PreceptorCurso real)
# =========================================================
def _preceptor_can_access_alumno(user, alumno: Alumno) -> bool:
    """
    Permite acceso a preceptor SOLO si el alumno pertenece a un curso asignado a ese preceptor.
    """
    curso_alumno = getattr(alumno, "curso", None)
    if not curso_alumno or PreceptorCurso is None:
        return False

    try:
        school_ref = getattr(alumno, "school", None)
        refs = _preceptor_assignment_refs(user, school=school_ref)
        return course_ref_matches(refs, obj=alumno)
    except Exception:
        return False


def _preceptor_can_access_curso(user, curso: str = "", school=None, school_course=None) -> bool:
    curso = (curso or "").strip()
    if (not curso and school_course is None) or PreceptorCurso is None:
        return False

    try:
        refs = _preceptor_assignment_refs(user, school=school)
        return course_ref_matches(
            refs,
            school=school,
            school_course_id=getattr(school_course, "id", None),
            course_code=curso,
        )
    except Exception:
        return False


def _assignment_cache_user_fragment(user) -> str:
    user_id = getattr(user, "id", None)
    username = str(getattr(user, "username", "") or "").strip().lower() or "anon"
    return f"{user_id or 'x'}:{username}"


def _assignment_cache_scope_id(school) -> int:
    return int(getattr(school, "id", None) or 0)


def _assignment_cache_key(prefix: str, user, school=None) -> str:
    return f"views:{prefix}:u{_assignment_cache_user_fragment(user)}:s{_assignment_cache_scope_id(school)}"


def invalidate_assignment_cache_for_user(user, school=None):
    """Invalida todas las cachés de asignación de cursos para el usuario dado."""
    user_id = getattr(user, "id", None)
    school_id = _assignment_cache_scope_id(school)
    prefixes = [
        "preceptor_refs",
        "profesor_refs",
        "preceptor_course_options",
        "profesor_course_options",
    ]
    keys = [_assignment_cache_key(p, user, school) for p in prefixes]
    # También invalida la caché de alertas
    keys.append(f"alertas:v1:preceptor_refs:u{user_id or 'x'}:s{school_id}")
    try:
        cache.delete_many(keys)
    except Exception:
        for key in keys:
            try:
                cache.delete(key)
            except Exception:
                pass


def _serialize_course_refs(refs) -> tuple:
    return tuple(
        (
            getattr(ref, "school_id", None),
            getattr(ref, "school_course_id", None),
            str(getattr(ref, "course_code", "") or ""),
        )
        for ref in (refs or [])
    )


def _deserialize_course_refs(rows) -> list:
    out = []
    for row in rows or []:
        try:
            school_id, school_course_id, course_code = row
        except Exception:
            continue
        out.append(
            CourseRef(
                school_id=int(school_id) if school_id is not None else None,
                school_course_id=int(school_course_id) if school_course_id is not None else None,
                course_code=normalize_course_code(course_code),
            )
        )
    return out


def _profesor_assignment_refs(user, school=None):
    if ProfesorCurso is None:
        return []
    school_id = getattr(school, "id", None) or 0
    cache_attr = "_cached_profesor_assignment_refs_by_school"
    cached = getattr(user, cache_attr, None)
    if isinstance(cached, dict) and school_id in cached:
        return list(cached[school_id])
    cache_key = _assignment_cache_key("profesor_refs", user, school=school)
    try:
        shared_cached = cache.get(cache_key)
        if shared_cached is not None:
            refs = _deserialize_course_refs(shared_cached)
            try:
                if not isinstance(cached, dict):
                    cached = {}
                cached[school_id] = tuple(refs)
                setattr(user, cache_attr, cached)
            except Exception:
                pass
            return refs
    except Exception:
        pass
    try:
        qs = ProfesorCurso.objects.filter(profesor=user)
        if school is not None:
            qs = scope_queryset_to_school(qs, school)
        refs = get_assignment_course_refs(qs)
    except Exception:
        refs = []
    try:
        if not isinstance(cached, dict):
            cached = {}
        cached[school_id] = tuple(refs)
        setattr(user, cache_attr, cached)
    except Exception:
        pass
    try:
        cache.set(cache_key, _serialize_course_refs(refs), ASSIGNMENT_REFS_CACHE_TTL)
    except Exception:
        pass
    return refs


def _preceptor_assignment_refs(user, school=None):
    if PreceptorCurso is None:
        return []
    school_id = getattr(school, "id", None) or 0
    cache_attr = "_cached_preceptor_assignment_refs_by_school"
    cached = getattr(user, cache_attr, None)
    if isinstance(cached, dict) and school_id in cached:
        return list(cached[school_id])
    cache_key = _assignment_cache_key("preceptor_refs", user, school=school)
    try:
        shared_cached = cache.get(cache_key)
        if shared_cached is not None:
            refs = _deserialize_course_refs(shared_cached)
            try:
                if not isinstance(cached, dict):
                    cached = {}
                cached[school_id] = tuple(refs)
                setattr(user, cache_attr, cached)
            except Exception:
                pass
            return refs
    except Exception:
        pass
    try:
        qs = PreceptorCurso.objects.filter(preceptor=user)
        if school is not None:
            qs = scope_queryset_to_school(qs, school)
        refs = get_assignment_course_refs(qs)
    except Exception:
        refs = []
    try:
        if not isinstance(cached, dict):
            cached = {}
        cached[school_id] = tuple(refs)
        setattr(user, cache_attr, cached)
    except Exception:
        pass
    try:
        cache.set(cache_key, _serialize_course_refs(refs), ASSIGNMENT_REFS_CACHE_TTL)
    except Exception:
        pass
    return refs


def _assignment_course_options(qs, *, user, school=None, cache_prefix: str):
    school_id = _assignment_cache_scope_id(school)
    cache_attr = f"_cached_{cache_prefix}_course_options_by_school"
    cached = getattr(user, cache_attr, None)
    if isinstance(cached, dict) and school_id in cached:
        return [dict(item) for item in cached[school_id]]

    cache_key = _assignment_cache_key(f"{cache_prefix}_course_options", user, school=school)
    try:
        shared_cached = cache.get(cache_key)
        if shared_cached is not None:
            options = [dict(item) for item in (shared_cached or [])]
            try:
                if not isinstance(cached, dict):
                    cached = {}
                cached[school_id] = tuple(dict(item) for item in options)
                setattr(user, cache_attr, cached)
            except Exception:
                pass
            return options
    except Exception:
        pass

    out = []
    seen = set()
    missing_catalog_data = False
    try:
        rows = qs.values_list(
            "school_course_id",
            "school_course__code",
            "school_course__name",
            "curso",
        )
    except Exception:
        rows = []

    for school_course_id, school_course_code, school_course_name, curso in rows:
        code = normalize_course_code(school_course_code or curso)
        if not code:
            continue
        key = (school_course_id, code)
        if key in seen:
            continue
        seen.add(key)
        nombre = str(school_course_name or code).strip() or code
        if school_course_id is None or not school_course_name:
            missing_catalog_data = True
        out.append(
            {
                "school_course_id": school_course_id,
                "code": code,
                "nombre": nombre,
            }
        )

    if missing_catalog_data and out:
        catalog_options = _school_course_options_for_ui(school=school)
        by_id = {
            option.get("school_course_id"): dict(option)
            for option in catalog_options
            if option.get("school_course_id") is not None
        }
        by_code = {
            normalize_course_code(option.get("code") or option.get("id")): dict(option)
            for option in catalog_options
            if normalize_course_code(option.get("code") or option.get("id"))
        }
        merged = []
        for option in out:
            resolved = None
            option_id = option.get("school_course_id")
            option_code = normalize_course_code(option.get("code"))
            if option_id is not None:
                resolved = by_id.get(option_id)
            if resolved is None and option_code:
                resolved = by_code.get(option_code)
            if resolved is not None:
                merged.append(
                    {
                        "school_course_id": resolved.get("school_course_id"),
                        "code": normalize_course_code(resolved.get("code") or resolved.get("id")),
                        "nombre": str(resolved.get("nombre") or option_code).strip() or option_code,
                    }
                )
            else:
                merged.append(option)
        out = merged

    try:
        if not isinstance(cached, dict):
            cached = {}
        cached[school_id] = tuple(dict(item) for item in out)
        setattr(user, cache_attr, cached)
    except Exception:
        pass
    try:
        cache.set(cache_key, tuple(dict(item) for item in out), ASSIGNMENT_REFS_CACHE_TTL)
    except Exception:
        pass
    return [dict(item) for item in out]


def _profesor_assignment_course_options(user, *, school=None):
    if ProfesorCurso is None:
        return []
    qs = ProfesorCurso.objects.filter(profesor=user)
    if school is not None:
        qs = scope_queryset_to_school(qs, school)
    return _assignment_course_options(qs, user=user, school=school, cache_prefix="profesor")


def _preceptor_assignment_course_options(user, *, school=None):
    if PreceptorCurso is None:
        return []
    qs = PreceptorCurso.objects.filter(preceptor=user)
    if school is not None:
        qs = scope_queryset_to_school(qs, school)
    return _assignment_course_options(qs, user=user, school=school, cache_prefix="preceptor")


def _school_course_options_for_ui(*, school=None, allowed_codes=None):
    allowed = {
        str(code or "").strip().upper()
        for code in (allowed_codes or [])
        if str(code or "").strip()
    }
    options = get_school_course_dicts(
        school=school,
        fallback_to_defaults=False,
        catalog_only=True,
    )
    out = []
    for option in options:
        code = str(option.get("code") or option.get("id") or "").strip()
        if not code:
            continue
        if allowed and code.upper() not in allowed:
            continue
        out.append(
            {
                "school_course_id": option.get("school_course_id"),
                "code": code,
                "nombre": str(option.get("nombre") or code),
            }
        )
    return out


def _profile_assigned_school_courses(*, user, groups, school=None, preview_role=None):
    effective_groups = {str(group or "").strip() for group in (groups or []) if str(group or "").strip()}

    if "Directivos" in effective_groups:
        return _school_course_options_for_ui(school=school)

    if "Preceptores" in effective_groups:
        options = _preceptor_assignment_course_options(user, school=school)
        if options:
            return options
        if preview_role and getattr(user, "is_superuser", False):
            return _school_course_options_for_ui(school=school)[:1]
        return []

    if "Profesores" in effective_groups:
        options = _profesor_assignment_course_options(user, school=school)
        if options:
            return options
        if preview_role and getattr(user, "is_superuser", False):
            return _school_course_options_for_ui(school=school)[:1]
        return []

    return []


def _resolve_request_course_selection(
    request,
    *,
    school=None,
    required=False,
    allow_all_markers=False,
):
    raw_course = (
        request.POST.get("curso")
        or request.GET.get("curso")
        or ""
    )
    raw_school_course_id = (
        request.POST.get("school_course_id")
        or request.GET.get("school_course_id")
        or ""
    )
    school_course, course_code, error = resolve_course_reference(
        school=school,
        raw_course=raw_course,
        raw_school_course_id=raw_school_course_id,
        required=required,
        allow_all_markers=allow_all_markers,
    )
    return {
        "school_course": school_course,
        "school_course_id": getattr(school_course, "id", None),
        "course_code": course_code,
        "error": error,
    }


def _course_selection_querystring(*, school_course_id=None, course_code="") -> str:
    if school_course_id not in (None, "", []):
        return f"?school_course_id={school_course_id}"
    if str(course_code or "").strip().upper() in {"ALL", "TODOS", "*"}:
        return f"?curso={course_code}"
    return ""


def _course_payload(*, school=None, course_code="", school_course=None):
    resolved_code = str(course_code or "").strip().upper()
    resolved_school_course = school_course
    if resolved_school_course is None and school is not None and resolved_code:
        resolved_school_course = resolve_school_course_for_value(school=school, curso=resolved_code)

    if resolved_school_course is not None:
        resolved_code = str(getattr(resolved_school_course, "code", "") or resolved_code).strip().upper()
        course_name = (
            str(getattr(resolved_school_course, "name", "") or "").strip()
            or resolved_code
            or None
        )
    else:
        course_name = get_course_label(resolved_code, school=school) if resolved_code else None

    return {
        "curso": resolved_code or None,
        "school_course_id": getattr(resolved_school_course, "id", None),
        "school_course_name": course_name,
    }


def _public_course_payload(*, school=None, course_code="", school_course=None):
    return {
        key: value
        for key, value in _course_payload(
            school=school,
            course_code=course_code,
            school_course=school_course,
        ).items()
        if key != "curso"
    }


def _public_course_payload_from_option(option: dict) -> dict:
    payload = _course_option_payload(option)
    return {
        "school_course_id": payload.get("school_course_id"),
        "school_course_name": payload.get("nombre"),
    }


def _course_option_payload(option: dict) -> dict:
    code = str(option.get("code") or option.get("id") or "").strip().upper()
    nombre = str(option.get("nombre") or code).strip() or code
    return {
        "id": code,
        "code": code,
        "nombre": nombre,
        "school_course_id": option.get("school_course_id"),
    }


def _resolve_path_course_selection(
    raw_value,
    *,
    school=None,
    required=False,
    deprecated_course_error=None,
):
    raw = str(raw_value or "").strip()
    if not raw:
        if required:
            return {
                "school_course": None,
                "school_course_id": None,
                "course_code": "",
                "error": "Falta el campo requerido: school_course_id o curso.",
            }
        return {
            "school_course": None,
            "school_course_id": None,
            "course_code": "",
            "error": None,
        }

    school_course = get_school_course_by_id(raw, school=school, include_inactive=True)
    if school_course is not None:
        return {
            "school_course": school_course,
            "school_course_id": school_course.id,
            "course_code": str(getattr(school_course, "code", "") or "").strip().upper(),
            "error": None,
        }

    school_course, course_code, error = resolve_course_reference(
        school=school,
        raw_course=raw,
        required=required,
        deprecated_course_error=deprecated_course_error,
    )
    return {
        "school_course": school_course,
        "school_course_id": getattr(school_course, "id", None),
        "course_code": course_code,
        "error": error,
    }


def _profesor_can_access_curso(user, curso: str = "", school=None, school_course=None) -> bool:
    curso = (curso or "").strip()
    if not curso and school_course is None:
        return False

    if ProfesorCurso is None:
        return True

    try:
        refs = _profesor_assignment_refs(user, school=school)
        if not refs:
            return True
        return course_ref_matches(
            refs,
            school=school,
            school_course_id=getattr(school_course, "id", None),
            course_code=curso,
        )
    except Exception:
        return True


def _profesor_can_access_alumno(user, alumno: Alumno) -> bool:
    school_course = getattr(alumno, "school_course", None)
    curso_alumno = getattr(school_course, "code", None) or getattr(alumno, "curso", None)
    if not curso_alumno and school_course is None:
        return False
    return _profesor_can_access_curso(
        user,
        curso_alumno,
        school=getattr(alumno, "school", None),
        school_course=school_course,
    )


def _can_access_course_roster(request, curso: str, *, school_course=None) -> bool:
    user = request.user
    active_school = get_request_school(request)
    if getattr(user, "is_superuser", False):
        return True
    if _has_role(request, "Directivos"):
        return True
    if _has_role(request, "Preceptores"):
        return _preceptor_can_access_curso(
            user,
            curso,
            school=active_school,
            school_course=school_course,
        )
    if _has_role(request, "Profesores"):
        return _profesor_can_access_curso(
            user,
            curso,
            school=active_school,
            school_course=school_course,
        )
    return False


def _can_access_alumno_data(request, alumno: Alumno) -> bool:
    from ..contexto import resolve_alumno_for_user

    user = request.user
    if getattr(user, "is_superuser", False):
        return True
    if _has_role(request, "Directivos"):
        return True
    if getattr(alumno, "padre_id", None) == getattr(user, "id", None):
        return True
    if _has_role(request, "Preceptores") and _preceptor_can_access_alumno(user, alumno):
        return True
    if _has_role(request, "Profesores") and _profesor_can_access_alumno(user, alumno):
        return True

    try:
        if getattr(alumno, "usuario_id", None) == user.id:
            return True
    except Exception:
        pass

    try:
        resolution = resolve_alumno_for_user(user, school=get_request_school(request))
        return bool(resolution.alumno and resolution.alumno.id == alumno.id)
    except Exception:
        return False


# =========================================================
#  ✅ NUEVO: Compat Mensaje (emisor/receptor vs remitente/destinatario)
# =========================================================
@lru_cache(maxsize=1)
def _mensaje_sender_field() -> str:
    return "remitente" if _has_model_field(Mensaje, "remitente") else "emisor"


@lru_cache(maxsize=1)
def _mensaje_recipient_field() -> str:
    return "destinatario" if _has_model_field(Mensaje, "destinatario") else "receptor"


def _mensajes_inbox_qs(user, school=None):
    rf = _mensaje_recipient_field()
    return scope_queryset_to_school(Mensaje.objects.filter(**{rf: user}), school)


def _mensajes_sent_qs(user, school=None):
    sf = _mensaje_sender_field()
    return scope_queryset_to_school(Mensaje.objects.filter(**{sf: user}), school)


def _mensajes_unread_count_from_qs(inbox_qs) -> int:
    has_leido = _has_model_field(Mensaje, "leido")
    has_leido_en = _has_model_field(Mensaje, "leido_en")
    if has_leido and has_leido_en:
        return inbox_qs.filter(Q(leido=False) | Q(leido_en__isnull=True)).count()
    if has_leido:
        return inbox_qs.filter(leido=False).count()
    if has_leido_en:
        return inbox_qs.filter(leido_en__isnull=True).count()
    if _has_model_field(Mensaje, "fecha_lectura"):
        return inbox_qs.filter(fecha_lectura__isnull=True).count()
    return 0


def _mensajes_count_stats_from_qs(inbox_qs) -> tuple:
    has_leido = _has_model_field(Mensaje, "leido")
    has_leido_en = _has_model_field(Mensaje, "leido_en")
    if has_leido and has_leido_en:
        stats = inbox_qs.aggregate(
            received=Count("id"),
            unread=Count("id", filter=Q(leido=False) | Q(leido_en__isnull=True)),
        )
        return int(stats.get("received") or 0), int(stats.get("unread") or 0)
    if has_leido:
        stats = inbox_qs.aggregate(
            received=Count("id"),
            unread=Count("id", filter=Q(leido=False)),
        )
        return int(stats.get("received") or 0), int(stats.get("unread") or 0)
    if has_leido_en:
        stats = inbox_qs.aggregate(
            received=Count("id"),
            unread=Count("id", filter=Q(leido_en__isnull=True)),
        )
        return int(stats.get("received") or 0), int(stats.get("unread") or 0)
    if _has_model_field(Mensaje, "fecha_lectura"):
        stats = inbox_qs.aggregate(
            received=Count("id"),
            unread=Count("id", filter=Q(fecha_lectura__isnull=True)),
        )
        return int(stats.get("received") or 0), int(stats.get("unread") or 0)
    return int(inbox_qs.count()), 0
