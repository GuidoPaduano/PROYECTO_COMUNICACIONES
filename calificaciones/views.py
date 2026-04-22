# calificaciones/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import ValidationError
from django.core.cache import cache

from datetime import date
from django.utils.dateparse import parse_date
from django.utils import timezone

from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from .jwt_auth import CookieJWTAuthentication as JWTAuthentication
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
from rest_framework.decorators import (
    api_view, authentication_classes, permission_classes, parser_classes, throttle_classes
)
from rest_framework.throttling import UserRateThrottle

from reportlab.pdfgen import canvas

from django.db.models import Q, Count  # âœ… NUEVO (para filtros robustos de no leÃ­dos)
from functools import lru_cache

from .course_access import (
    CourseRef,
    assignment_matches_course,
    build_course_membership_q,
    course_ref_matches,
    filter_course_options_by_refs,
    get_assignment_course_refs,
    normalize_course_code,
)
from .models import Alumno, Nota, Mensaje, Evento, Asistencia, Notificacion, SchoolCourse, resolve_school_course_for_value
from .utils_cursos import get_course_label, get_school_course_by_id, get_school_course_choices, get_school_course_dicts, resolve_course_reference
from .serializers import AlumnoFullSerializer, NotaCreateSerializer, NotaPublicSerializer
from .forms import EventoForm as BaseEventoForm, NotaForm
from .constants import MATERIAS
from .contexto import resolve_alumno_for_user
from .schools import (
    get_available_school_dicts_for_user,
    get_request_school,
    school_to_dict,
    scope_queryset_to_school,
)
from .user_groups import get_user_group_names
from django.contrib.auth import logout as dj_logout, update_session_auth_hash
from django.contrib.auth import get_user_model
from .auth_api import clear_auth_cookies

import json
import logging

logger = logging.getLogger(__name__)
ASSIGNMENT_REFS_CACHE_TTL = 120

try:
    # âœ… NUEVO: si existen los modelos reales preceptor/profesorâ†’cursos, los usamos para permisos
    from .models_preceptores import PreceptorCurso, ProfesorCurso  # type: ignore
except Exception:
    PreceptorCurso = None
    ProfesorCurso = None


# =========================================================
#  Notificaciones por NOTA (campanita: Notificacion del sistema)
# =========================================================

def _resolver_destinatario_padre(alumno):
    """Destinatario para notificaciÃ³n.

    Preferencia: Alumno.padre (FK real)
    Fallback por username==id_alumno
    """
    padre = getattr(alumno, "padre", None)
    if padre:
        return padre, "alumno.padre"

    try:
        User = get_user_model()
        legajo = (getattr(alumno, "id_alumno", "") or "").strip()
        if not legajo:
            return None, None
        u = User.objects.filter(username__iexact=legajo).first()
        if u:
            return u, "username==id_alumno"
    except Exception:
        return None, None

    return None, None


def _resolver_destinatarios_notif(alumno):
    """Destinatarios para notificaciones (campanita) relacionadas al alumno.

    - Padre asignado (alumno.padre) si existe
    - Alumno.usuario si existe
    - Fallback: User.username == alumno.id_alumno (legajo)

    (sin duplicados)
    """
    destinatarios = []
    seen = set()

    def _add(u):
        try:
            if u is None:
                return
            uid = getattr(u, "id", None)
            if uid is None or uid in seen:
                return
            seen.add(uid)
            destinatarios.append(u)
        except Exception:
            pass

    # Padre
    _add(getattr(alumno, "padre", None))

    # Alumno (vÃ­nculo explÃ­cito)
    _add(getattr(alumno, "usuario", None))

    # Alumno por convenciÃ³n username==legajo
    try:
        User = get_user_model()
        legajo = (getattr(alumno, "id_alumno", "") or "").strip()
        if legajo:
            _add(User.objects.filter(username__iexact=legajo).first())
    except Exception:
        pass

    # Ultimo intento: resolver destinatario por legajo
    if not destinatarios:
        try:
            u_fb, _src = _resolver_destinatario_padre(alumno)
            _add(u_fb)
        except Exception:
            pass

    return destinatarios


def _notification_course_name(*, alumno=None, school_course=None, course_code="", school=None):
    resolved_school_course = school_course or getattr(alumno, "school_course", None)
    return (
        getattr(resolved_school_course, "name", None)
        or getattr(resolved_school_course, "code", None)
        or get_course_label(
            course_code or getattr(alumno, "curso", ""),
            school=school or getattr(alumno, "school", None),
        )
        or course_code
        or getattr(alumno, "curso", None)
        or None
    )


def _notification_course_meta(*, alumno=None, school_course=None, course_code="", school=None):
    return {
        "school_course_id": getattr(school_course, "id", None) or getattr(alumno, "school_course_id", None),
        "school_course_name": _notification_course_name(
            alumno=alumno,
            school_course=school_course,
            course_code=course_code,
            school=school,
        ),
    }


def _notify_padre_por_nota(remitente, nota, *, silent=True):
    """Crea una Notificacion del sistema (campanita) al padre/tutor del alumno informando una NOTA.

    Importante:
    - NO crea un Mensaje (bandeja de entrada).
    - La bandeja queda solo para mensajerÃ­a real entre usuarios.
    """
    try:
        alumno = getattr(nota, "alumno", None)
        if not alumno:
            return False

        destinatarios = _resolver_destinatarios_notif(alumno)
        if not destinatarios:
            return False

        # Nombre consistente (el modelo Alumno del proyecto no tiene 'apellido', pero dejamos fallback por si aparece)
        nombre = (f"{getattr(alumno, 'apellido', '')}, {getattr(alumno, 'nombre', '')}").strip(", ").strip()
        if not nombre:
            nombre = (getattr(alumno, "nombre", "") or "").strip() or str(getattr(alumno, "id_alumno", ""))

        curso = (getattr(alumno, "curso", "") or "").strip()
        course_name = _notification_course_name(alumno=alumno, course_code=curso)
        materia = (getattr(nota, "materia", "") or "").strip()
        tipo = (getattr(nota, "tipo", "") or "").strip()
        calif = (getattr(nota, "calificacion", "") or "").strip()
        cuatri = getattr(nota, "cuatrimestre", None)
        fecha = getattr(nota, "fecha", None)
        obs = (getattr(nota, "observaciones", "") or "").strip()

        titulo = f"Nueva nota para {nombre}"

        # DescripciÃ³n compacta (no hace falta que parezca un email)
        parts = []
        parts.append("Se registrÃ³ una nueva calificaciÃ³n.")
        if course_name:
            parts.append(f"Curso: {course_name}")
        if materia:
            parts.append(f"Materia: {materia}")
        if tipo:
            parts.append(f"Tipo: {tipo}")
        if calif:
            parts.append(f"CalificaciÃ³n: {calif}")
        if cuatri:
            parts.append(f"Cuatrimestre: {cuatri}")
        if hasattr(fecha, "isoformat"):
            parts.append(f"Fecha: {fecha.isoformat()}")
        if obs:
            parts.append(f"Obs: {obs}")

        descripcion = " Â· ".join([p for p in parts if p]).strip()

        # URL destino (Parte B/C usan esto)
        url = f"/alumnos/{alumno.id}/?tab=notas"

        for destinatario in destinatarios:
            Notificacion.objects.create(
                school=getattr(alumno, "school", None),
                destinatario=destinatario,
                tipo="nota",
                titulo=titulo,
                descripcion=descripcion,
                url=url,
                meta={
                    "alumno_id": alumno.id,
                    "nota_id": getattr(nota, "id", None),
                    **_notification_course_meta(alumno=alumno, course_code=curso),
                },
                leida=False,
            )
        return True
    except Exception:
        if silent:
            return False
        raise


def _notify_padres_por_notas_bulk(remitente, notas, *, silent=True):
    """NotificaciÃ³n optimizada: 1 Notificacion por ALUMNO (campanita), sin ensuciar bandeja.

    Devuelve cantidad de notificaciones creadas.
    """
    try:
        if not notas:
            return 0

        grupos = {}
        for n in notas:
            alumno = getattr(n, "alumno", None)
            if not alumno:
                continue

            # âœ… Igual que en la API: notificamos a PADRE y ALUMNO (si existe vÃ­nculo)
            destinatarios = _resolver_destinatarios_notif(alumno)
            if not destinatarios:
                continue

            for destinatario in destinatarios:
                key = (getattr(destinatario, "id", None), getattr(alumno, "id", None))
                if key not in grupos:
                    nombre = (f"{getattr(alumno, 'apellido', '')}, {getattr(alumno, 'nombre', '')}").strip(", ").strip()
                    if not nombre:
                        nombre = (getattr(alumno, "nombre", "") or "").strip() or str(getattr(alumno, "id_alumno", ""))

                    grupos[key] = {
                        "dest": destinatario,
                        "alumno": alumno,
                        "nombre": nombre,
                        "curso": (getattr(alumno, "curso", "") or "").strip(),
                        "notas": [],
                    }

                grupos[key]["notas"].append(n)

        if not grupos:
            return 0

        notifs = []

        for g in grupos.values():
            alumno = g["alumno"]
            nombre = g["nombre"]
            curso = g["curso"]
            course_name = _notification_course_name(alumno=alumno, course_code=curso)
            notas_alumno = g["notas"]

            titulo = f"Nueva nota para {nombre}" if len(notas_alumno) == 1 else f"Nuevas notas para {nombre}"

            # Orden lindo
            try:
                notas_alumno = sorted(
                    notas_alumno,
                    key=lambda x: (
                        getattr(x, "fecha", None) or timezone.localdate(),
                        getattr(x, "materia", ""),
                    ),
                )
            except Exception:
                pass

            lines = []
            for nn in notas_alumno:
                materia = (getattr(nn, "materia", "") or "").strip()
                tipo = (getattr(nn, "tipo", "") or "").strip()
                calif = (getattr(nn, "calificacion", "") or "").strip()
                fecha = getattr(nn, "fecha", None)
                fstr = fecha.isoformat() if hasattr(fecha, "isoformat") else ""

                base = f"â€¢ {materia} ({tipo}): {calif}".strip()
                if fstr:
                    base += f" â€” {fstr}"
                lines.append(base)

            descripcion = "Se registraron nuevas calificaciones."
            if course_name:
                descripcion += f" Curso: {course_name}."
            if lines:
                # Guardamos en texto (la UI lo truncarÃ¡ si hace falta)
                descripcion += " " + " ".join(lines)

            url = f"/alumnos/{alumno.id}/?tab=notas"

            notifs.append(
                Notificacion(
                    school=getattr(alumno, "school", None),
                    destinatario=g["dest"],
                    tipo="nota",
                    titulo=titulo,
                    descripcion=descripcion,
                    url=url,
                    meta={
                        "alumno_id": alumno.id,
                        "nota_ids": [getattr(x, "id", None) for x in notas_alumno],
                        **_notification_course_meta(alumno=alumno, course_code=curso),
                    },
                    leida=False,
                )
            )

        if notifs:
            Notificacion.objects.bulk_create(notifs)

        return len(notifs)
    except Exception:
        if silent:
            return 0
        raise



# ============================================================
# Helper: Vista previa de rol (â€œVista comoâ€¦â€) para superusuario
# ============================================================
def _get_preview_role(request):
    """
    Devuelve un rol de vista previa si el usuario es superusuario y pidiÃ³ simular un rol.
    Lee `view_as` (querystring) o el header `X-Preview-Role`.
    Valores vÃ¡lidos: 'Profesores', 'Preceptores', 'Directivos', 'Padres', 'Alumnos'.
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
    """Intenta parsear JSON manualmente si request.data viene vacÃ­o."""
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
    return "â€”"


def _alumno_to_dict(a: Alumno):
    if not a:
        return None
    school_course = getattr(a, "school_course", None)
    return {
        "id": a.id,
        "id_alumno": getattr(a, "id_alumno", None),
        "nombre": a.nombre,
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
#  âœ… NUEVO: permisos de PRECEPTOR por curso (PreceptorCurso real)
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


def _serialize_course_refs(refs) -> tuple[tuple[int | None, int | None, str], ...]:
    return tuple(
        (
            getattr(ref, "school_id", None),
            getattr(ref, "school_course_id", None),
            str(getattr(ref, "course_code", "") or ""),
        )
        for ref in (refs or [])
    )


def _deserialize_course_refs(rows) -> list[CourseRef]:
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
#  âœ… NUEVO: Compat Mensaje (emisor/receptor vs remitente/destinatario)
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


def _mensajes_count_stats_from_qs(inbox_qs) -> tuple[int, int]:
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


# =========================================================
#  Vistas HTML / Index
# =========================================================
@login_required
def index(request):
    # Usa roles efectivos (respetan vista previa)
    active_school = get_request_school(request)
    is_padre = _has_role(request, 'Padres')
    is_staff_role = _has_role(request, 'Profesores', 'Directivos', 'Preceptores') or request.user.is_superuser
    puede_pasar_asistencia = bool(
        request.user.is_superuser
        or (
            _has_role(request, 'Preceptores')
            and _preceptor_assignment_refs(request.user, school=active_school)
        )
    )

    if not (is_padre or is_staff_role):
        return HttpResponse("No tienes permiso.", status=403)

    return render(
        request,
        'calificaciones/index.html',
        {
            "is_padre": is_padre,
            "is_staff_role": is_staff_role,
            "puede_pasar_asistencia": puede_pasar_asistencia,
        },
    )


# =========================================================
#  PERFIL API (GET+PATCH) para Next.js â€” JWT o sesiÃ³n
# =========================================================
@csrf_exempt
@api_view(["GET", "PATCH"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def perfil_api(request):
    """
    - GET: datos del usuario + contexto (alumno propio, hijos, preceptor, contadores)
    - PATCH: actualiza first_name, last_name, email del usuario autenticado.
    """
    user = request.user
    active_school = get_request_school(request)

    # ===== Vista previa de rol (â€œVista comoâ€¦â€) para superusuario =====
    try:
        preview_role = _get_preview_role(request)
    except Exception:
        preview_role = None

    # Grupos efectivos
    grupos_reales = list(get_user_group_names(user))
    grupos = [preview_role] if preview_role else grupos_reales

    # Rol real + rol efectivo para UI
    try:
        rol_real = _rol_principal(user)
    except Exception:
        rol_real = grupos_reales[0] if grupos_reales else "â€”"
    rol = preview_role if preview_role else rol_real

    # ===== Contextos =====
    alumno_propio = None
    children = []
    assigned_school_courses = _profile_assigned_school_courses(
        user=user,
        groups=grupos,
        school=active_school,
        preview_role=preview_role,
    )
    alumno_select_qs = scope_queryset_to_school(
        Alumno.objects.select_related("school_course"),
        active_school,
    )

    # Alumno (resolucion tolerante)
    if "Alumnos" in grupos:
        r = resolve_alumno_for_user(user, school=active_school)
        if r.alumno:
            alumno_propio = _alumno_to_dict(r.alumno)
        else:
            # Fallback para vista previa: tomar cualquier alumno
            if preview_role:
                a0 = alumno_select_qs.order_by('id').first()
                alumno_propio = _alumno_to_dict(a0) if a0 else None

    # Padre
    if "Padres" in grupos:
        try:
            hijos = alumno_select_qs.filter(padre=user).order_by('curso', 'nombre')
            children = [_alumno_to_dict(x) for x in hijos]
        except Exception:
            children = []
        # Fallback vista previa: elegir un padre real y listar sus hijos
        if preview_role and not children:
            a0 = alumno_select_qs.filter(padre__isnull=False).order_by('padre_id').first()
            if a0 and a0.padre_id:
                hijos = alumno_select_qs.filter(padre_id=a0.padre_id).order_by('curso', 'nombre')
                children = [_alumno_to_dict(x) for x in hijos]

    # ===== PATCH =====
    if request.method == "PATCH":
        payload = _coerce_json(request)
        first_name = (payload.get("first_name") or "").strip()
        last_name = (payload.get("last_name") or "").strip()
        email = (payload.get("email") or "").strip()

        changed = False
        if first_name or first_name == "":
            user.first_name = first_name
            changed = True
        if last_name or last_name == "":
            user.last_name = last_name
            changed = True
        if email:
            # Evitar emails duplicados
            try:
                User = get_user_model()
                if User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
                    return JsonResponse({"detail": "Ese correo ya estÃ¡ en uso."}, status=400)
            except Exception:
                pass
            user.email = email
            changed = True

        if changed:
            try:
                user.full_clean(exclude=['password'])
            except Exception:
                return JsonResponse({"detail": "Datos invÃ¡lidos"}, status=400)
            user.save()

    # ===== Stats =====
    if "Alumnos" in grupos and alumno_propio:
        notas_count = scope_queryset_to_school(Nota.objects.filter(alumno_id=alumno_propio["id"]), active_school).count()
    elif "Padres" in grupos and children:
        notas_count = scope_queryset_to_school(
            Nota.objects.filter(alumno_id__in=[a["id"] for a in children]),
            active_school,
        ).count()
    else:
        notas_count = 0

    # Mensajes: unificar variantes de emisor/receptor
    inbox_qs = _mensajes_inbox_qs(user, school=active_school)
    sent_qs = _mensajes_sent_qs(user, school=active_school)

    mensajes_recibidos, mensajes_no_leidos = _mensajes_count_stats_from_qs(inbox_qs)
    mensajes_enviados = sent_qs.count()

    data = {
        "user": {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "is_superuser": user.is_superuser,
            "groups": grupos,   # efectivos
            "rol": rol,         # efectivo
        },
        "alumno": alumno_propio,
        "children": children,
        "assigned_school_courses": assigned_school_courses,
        "school": school_to_dict(active_school),
        "available_schools": get_available_school_dicts_for_user(user, active_school=active_school),
        "stats": {
            "notas_count": notas_count,
            "mensajes_recibidos": mensajes_recibidos,
            "mensajes_no_leidos": mensajes_no_leidos,
            "mensajes_enviados": mensajes_enviados,
        },
    }
    return JsonResponse(data)


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
    - Superuser: si estÃ¡ en vista previa, se comporta como ese rol; si no, devuelve el curso pedido por
      `school_course_id`, o cae al primero disponible
    """
    user = request.user
    active_school = get_request_school(request)
    preview_role = _get_preview_role(request)
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
#  CatÃ¡logos/Alumnos para "Nueva nota"
# =========================================================
@csrf_exempt
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def notas_catalogos(request):
    """
    Devuelve catÃ¡logos base para la pantalla de "Nueva nota".
    - cursos: lista normalizada de `SchoolCourse` para el colegio activo
    - materias: lista desde constants.MATERIAS
    - tipos: (opcional) vacÃ­o por ahora; se puede poblar luego si definen choices
    """
    active_school = get_request_school(request)
    cursos = [
        _course_option_payload(option)
        for option in _school_course_options_for_ui(school=active_school)
    ]
    if _has_role(request, "Profesores") and not request.user.is_superuser:
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

    # âœ… FIX: si Alumno no tiene apellido, no explota
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

    Este endpoint solo acepta ids numericos de SchoolCourse en la ruta.
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


# =========================================================
#  ðŸ”Ž API Detalle de Alumno (preferir legajo sobre PK)
# =========================================================
@csrf_exempt
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def alumno_detalle(request, alumno_id):
    """
    GET /api/alumnos/<alumno_id>/

    Prioridad de resoluciÃ³n:
      1) Buscar por legajo `id_alumno` (string exacto).
      2) Si no existe y es numÃ©rico, intentar como PK (id interno).
    """
    active_school = get_request_school(request)
    alumnos_qs = scope_queryset_to_school(
        Alumno.objects.select_related("school", "school_course"),
        active_school,
    )

    try:
        # 1) intentar por legajo
        a = alumnos_qs.get(id_alumno=str(alumno_id))
    except Alumno.DoesNotExist:
        # 2) fallback a PK si es numÃ©rico
        if str(alumno_id).isdigit():
            try:
                a = alumnos_qs.get(pk=int(alumno_id))
            except Alumno.DoesNotExist:
                return Response({"detail": "No encontrado"}, status=404)
        else:
            return Response({"detail": "No encontrado"}, status=404)

    # âœ… NUEVO: autorizaciÃ³n consistente (incluye preceptor por curso)
    user = request.user
    is_padre = (getattr(a, "padre_id", None) == user.id)
    is_prof_ok = _has_role(request, "Profesores") and _profesor_can_access_alumno(user, a)
    is_prof_or_super = (user.is_superuser or is_prof_ok)
    # Alumno propio:
    # - VÃ­nculo explÃ­cito Alumno.usuario (si existe)
    # - Fallback robusto (username==legajo, padre con Ãºnico hijo, etc.)
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

    if not (is_padre or is_prof_or_super or is_alumno_mismo or is_preceptor_ok):
        return Response({"detail": "No autorizado"}, status=403)

    return Response(AlumnoFullSerializer(a).data)


# =========================================================
#  ðŸ“˜ API Notas de un alumno (preferir legajo sobre PK)
# =========================================================
@csrf_exempt
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def alumno_notas(request, alumno_id):
    """
    GET /api/alumnos/<alumno_id>/notas/

    Prioridad de resoluciÃ³n:
      1) Buscar por legajo `id_alumno`.
      2) Si no existe y es numÃ©rico, intentar como PK (id).
    """
    active_school = get_request_school(request)
    alumnos_qs = scope_queryset_to_school(Alumno.objects.all(), active_school)

    try:
        alumno = alumnos_qs.get(id_alumno=str(alumno_id))
    except Alumno.DoesNotExist:
        if str(alumno_id).isdigit():
            try:
                alumno = alumnos_qs.get(pk=int(alumno_id))
            except Alumno.DoesNotExist:
                return Response({"detail": "Alumno no encontrado"}, status=404)
        else:
            return Response({"detail": "Alumno no encontrado"}, status=404)

    user = request.user

    # Alumno propio (mismo criterio que en alumno_detalle)
    is_alumno_mismo = (getattr(alumno, "usuario_id", None) == user.id)
    if not is_alumno_mismo and "Alumnos" in viewer_groups:
        try:
            r = resolve_alumno_for_user(user, school=active_school)
            if r.alumno and r.alumno.id == alumno.id:
                is_alumno_mismo = True
        except Exception:
            pass

    # âœ… NUEVO: sumar Preceptores (pero solo si tienen el curso asignado)
    is_preceptor_ok = (
        ("Directivos" in viewer_groups)
        or ("Preceptores" in viewer_groups and _preceptor_can_access_alumno(user, alumno))
    )
    is_prof_ok = ("Profesores" in viewer_groups and _profesor_can_access_alumno(user, alumno))

    # AutorizaciÃ³n: superuser, profesores, preceptor por curso, padre o el propio alumno
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


# =========================================================
#  Notas
# =========================================================
@login_required
def agregar_nota(request):
    if not (_has_role(request, "Profesores") or request.user.is_superuser):
        return HttpResponse("No tenes permiso.", status=403)

    active_school = get_request_school(request)
    cursos = get_school_course_choices(school=active_school)
    selected_course = _resolve_request_course_selection(
        request,
        school=active_school,
        required=False,
    )
    if selected_course["error"]:
        return HttpResponse(selected_course["error"], status=400)
    curso_seleccionado = selected_course["course_code"]
    curso_seleccionado_id = selected_course["school_course_id"]
    if _has_role(request, "Profesores") and not request.user.is_superuser:
        assigned_refs = _profesor_assignment_refs(request.user, school=active_school)
        if assigned_refs:
            cursos = filter_course_options_by_refs(cursos, assigned_refs)
            if (curso_seleccionado_id or curso_seleccionado) and not course_ref_matches(
                assigned_refs,
                school_course_id=curso_seleccionado_id,
                course_code=curso_seleccionado,
            ):
                return HttpResponse("No tenes permiso para ese curso.", status=403)

    if request.method == "POST":
        alumnos_list = request.POST.getlist("alumno[]")

        if alumnos_list:
            materias_list = request.POST.getlist("materia[]")
            tipos_list = request.POST.getlist("tipo[]")
            califs_list = request.POST.getlist("calificacion[]")
            resultados_list = request.POST.getlist("resultado[]")
            notas_numericas_list = request.POST.getlist("nota_numerica[]")
            cuatris_list = request.POST.getlist("cuatrimestre[]")
            fechas_list = request.POST.getlist("fecha[]")

            creadas = 0
            errores = 0
            notas_creadas = []

            for i, alum_id_raw in enumerate(alumnos_list):
                alum_id = (alum_id_raw or "").strip()
                materia = (materias_list[i] or "").strip() if i < len(materias_list) else ""
                tipo = (tipos_list[i] or "").strip() if i < len(tipos_list) else ""
                calif = (califs_list[i] or "").strip() if i < len(califs_list) else ""
                resultado = (resultados_list[i] or "").strip() if i < len(resultados_list) else ""
                nota_numerica = (notas_numericas_list[i] or "").strip() if i < len(notas_numericas_list) else ""
                cuatr = (cuatris_list[i] or "").strip() if i < len(cuatris_list) else ""
                fstr = (fechas_list[i] or "").strip() if i < len(fechas_list) else ""
                fparsed = parse_date(fstr) if fstr else date.today()

                if not (alum_id and materia and tipo and cuatr):
                    errores += 1
                    continue

                try:
                    alumno = scope_queryset_to_school(Alumno.objects.all(), active_school).get(id_alumno=alum_id)
                except Alumno.DoesNotExist:
                    errores += 1
                    continue

                payload = {
                    "alumno": alumno.id,
                    "materia": materia,
                    "tipo": tipo,
                    "calificacion": calif,
                    "resultado": resultado,
                    "nota_numerica": nota_numerica,
                    "cuatrimestre": cuatr,
                    "fecha": (fparsed or date.today()).isoformat(),
                }
                ser = NotaCreateSerializer(data=payload)
                if ser.is_valid():
                    nota = ser.save(school=active_school or getattr(alumno, "school", None))
                    notas_creadas.append(nota)
                    creadas += 1
                else:
                    errores += 1

            try:
                _notify_padres_por_notas_bulk(request.user, notas_creadas)
            except Exception:
                pass

            if creadas:
                messages.success(request, f"Se guardaron {creadas} nota(s).")
            if errores:
                messages.error(request, f"{errores} fila(s) no pudieron guardarse. Revisa los datos.")
            return redirect(
                f"{request.path}{_course_selection_querystring(school_course_id=curso_seleccionado_id, course_code=curso_seleccionado or '')}"
            )

        alumno_id = request.POST.get("alumno")
        materia = request.POST.get("materia")
        tipo = request.POST.get("tipo")
        calificacion = request.POST.get("calificacion")
        resultado = request.POST.get("resultado")
        nota_numerica = request.POST.get("nota_numerica")
        cuatrimestre = request.POST.get("cuatrimestre")
        fecha_nota = parse_date(request.POST.get("fecha") or "") or date.today()

        try:
            alumno = scope_queryset_to_school(Alumno.objects.all(), active_school).get(id_alumno=alumno_id)
            payload = {
                "alumno": alumno.id,
                "materia": materia or "",
                "tipo": tipo or "",
                "calificacion": calificacion or "",
                "resultado": resultado or "",
                "nota_numerica": nota_numerica or "",
                "cuatrimestre": cuatrimestre,
                "fecha": fecha_nota.isoformat(),
            }
            ser = NotaCreateSerializer(data=payload)
            if not ser.is_valid():
                raise ValidationError(str(ser.errors))
            nota = ser.save(school=active_school or getattr(alumno, "school", None))

            try:
                _notify_padre_por_nota(request.user, nota)
            except Exception:
                pass

            messages.success(request, "Nota guardada correctamente.")
        except Alumno.DoesNotExist:
            messages.error(request, "Alumno no encontrado.")
        except ValidationError as e:
            messages.error(request, f"Carga invalida: {e}")
        except Exception as e:
            messages.error(request, f"No se pudo guardar la nota: {e}")
        return redirect("index")

    alumnos = []
    if curso_seleccionado:
        alumnos = _alumnos_por_curso_qs(curso_seleccionado, school=active_school).order_by("nombre")
    nota_form = NotaForm()
    nota_form.fields["alumno"].queryset = alumnos or Alumno.objects.none()

    return render(
        request,
        "calificaciones/agregar_nota.html",
        {
            "cursos": cursos,
            "curso_seleccionado": curso_seleccionado,
            "curso_seleccionado_id": curso_seleccionado_id,
            "alumnos": alumnos,
            "materias": MATERIAS,
            "resultados_catalogo": Nota.RESULTADO_CHOICES,
            "form": nota_form,
        },
    )


@csrf_exempt
@login_required
def agregar_nota_masiva(request):
    if not (_has_role(request, "Profesores") or request.user.is_superuser):
        return HttpResponse("No tenes permiso.", status=403)

    active_school = get_request_school(request)

    if request.method != "POST":
        return JsonResponse({"detail": "Metodo no permitido"}, status=405)

    if _has_role(request, "Profesores") and not request.user.is_superuser:
        assigned_refs = _profesor_assignment_refs(request.user, school=active_school)
        selected_course = _resolve_request_course_selection(
            request,
            school=active_school,
            required=False,
        )
        if selected_course["error"]:
            return JsonResponse({"detail": selected_course["error"]}, status=400)
        if assigned_refs:
            if (selected_course["school_course_id"] or selected_course["course_code"]) and not course_ref_matches(
                assigned_refs,
                school_course_id=selected_course["school_course_id"],
                course_code=selected_course["course_code"],
            ):
                return JsonResponse({"detail": "No autorizado para ese curso."}, status=403)
    else:
        selected_course = _resolve_request_course_selection(
            request,
            school=active_school,
            required=False,
        )
        if selected_course["error"]:
            return JsonResponse({"detail": selected_course["error"]}, status=400)

    alumnos_ids = request.POST.getlist("alumno[]")
    materias = request.POST.getlist("materia[]")
    tipos = request.POST.getlist("tipo[]")
    califs = request.POST.getlist("calificacion[]")
    resultados = request.POST.getlist("resultado[]")
    notas_numericas = request.POST.getlist("nota_numerica[]")
    cuatris = request.POST.getlist("cuatrimestre[]")
    fechas = request.POST.getlist("fecha[]")

    if not alumnos_ids and request.POST.get("alumno"):
        alumnos_ids = [request.POST.get("alumno")]
        materias = [request.POST.get("materia")]
        tipos = [request.POST.get("tipo")]
        califs = [request.POST.get("calificacion")]
        resultados = [request.POST.get("resultado")]
        notas_numericas = [request.POST.get("nota_numerica")]
        cuatris = [request.POST.get("cuatrimestre")]
        fechas = [request.POST.get("fecha")] if request.POST.get("fecha") else []

    if len(alumnos_ids) == 0:
        return JsonResponse({"creadas": 0, "detail": "Sin filas validas"}, status=400)

    errores = 0
    notas_creadas = []

    for i, alum_id_raw in enumerate(alumnos_ids):
        alum_id = (alum_id_raw or "").strip()
        materia = (materias[i] or "").strip() if i < len(materias) else ""
        tipo = (tipos[i] or "").strip() if i < len(tipos) else ""
        calif = (califs[i] or "").strip() if i < len(califs) else ""
        resultado = (resultados[i] or "").strip() if i < len(resultados) else ""
        nota_numerica = (notas_numericas[i] or "").strip() if i < len(notas_numericas) else ""
        cuatr = (cuatris[i] or "").strip() if i < len(cuatris) else ""
        f = parse_date(fechas[i]) if i < len(fechas) and fechas[i] else date.today()

        if not (alum_id and materia and tipo and cuatr):
            errores += 1
            continue

        try:
            alumno = scope_queryset_to_school(Alumno.objects.all(), active_school).get(id_alumno=alum_id)
        except Alumno.DoesNotExist:
            errores += 1
            continue

        payload = {
            "alumno": alumno.id,
            "materia": materia,
            "tipo": tipo,
            "calificacion": calif,
            "resultado": resultado,
            "nota_numerica": nota_numerica,
            "cuatrimestre": cuatr,
            "fecha": (f or date.today()).isoformat(),
        }
        ser = NotaCreateSerializer(data=payload)
        if ser.is_valid():
            notas_creadas.append(ser.save(school=active_school or getattr(alumno, "school", None)))
        else:
            errores += 1

    creadas = len(notas_creadas)
    if notas_creadas:
        try:
            _notify_padres_por_notas_bulk(request.user, notas_creadas)
        except Exception:
            pass

    accept = (request.headers.get("Accept") or "").lower()
    selected_course = _resolve_request_course_selection(
        request,
        school=active_school,
        required=False,
    )
    if selected_course["error"]:
        return JsonResponse({"detail": selected_course["error"]}, status=400)
    curso_qs = selected_course["course_code"] or ""
    curso_qs_id = selected_course["school_course_id"]
    if "text/html" in accept:
        return redirect(f"/agregar_nota{_course_selection_querystring(school_course_id=curso_qs_id, course_code=curso_qs)}")

    return JsonResponse({"creadas": creadas, "errores": errores})


@login_required
def ver_notas(request):
    # Permitir ver esta pantalla si la vista previa es "Padres"
    if _has_role(request, 'Padres') or request.user.is_superuser:
        active_school = get_request_school(request)
        alumnos_qs = scope_queryset_to_school(
            Alumno.objects.select_related("school_course"),
            active_school,
        )
        alumnos = alumnos_qs.filter(padre=request.user)

        # Fallback para vista previa: tomar un padre real y sus hijos si no hay vÃ­nculos
        if not alumnos.exists() and _get_preview_role(request):
            a0 = alumnos_qs.filter(padre__isnull=False).order_by('padre_id').first()
            if a0 and a0.padre_id:
                alumnos = alumnos_qs.filter(padre_id=a0.padre_id)

        notas = scope_queryset_to_school(
            Nota.objects.filter(alumno__in=alumnos).select_related("alumno", "alumno__school_course"),
            active_school,
        ).order_by('cuatrimestre')
        return render(request, 'calificaciones/ver_notas.html', {'notas': notas})
    else:
        return HttpResponse("No tienes permiso para ver notas.", status=403)


# =========================================================
#  MensajerÃ­a (HTML)
# =========================================================
@login_required
def enviar_mensaje(request):
    if not (_has_role(request, 'Profesores') or request.user.is_superuser):
        return HttpResponse("No tenÃ©s permiso.", status=403)

    active_school = get_request_school(request)
    cursos_disponibles = _school_course_options_for_ui(school=active_school)
    selected_course = _resolve_request_course_selection(
        request,
        school=active_school,
        required=False,
    )
    if selected_course["error"]:
        return HttpResponse(selected_course["error"], status=400)
    curso_seleccionado = selected_course["course_code"]
    curso_seleccionado_id = selected_course["school_course_id"]
    if _has_role(request, "Profesores") and not request.user.is_superuser:
        assigned_refs = _profesor_assignment_refs(request.user, school=active_school)
        if assigned_refs:
            cursos_disponibles = filter_course_options_by_refs(cursos_disponibles, assigned_refs)
            if (curso_seleccionado_id or curso_seleccionado) and not course_ref_matches(
                assigned_refs,
                school_course_id=curso_seleccionado_id,
                course_code=curso_seleccionado,
            ):
                return HttpResponse("No tenÃ©s permiso para ese curso.", status=403)
    alumnos = _alumnos_por_curso_qs(curso_seleccionado, school=active_school) if curso_seleccionado else []

    if request.method == 'POST':
        alumno_id = request.POST['alumno']
        asunto = request.POST['asunto']
        contenido = request.POST['contenido']
        try:
            alumno = scope_queryset_to_school(Alumno.objects.all(), active_school).get(id=int(alumno_id))
        except Exception:
            alumno = scope_queryset_to_school(Alumno.objects.all(), active_school).get(id_alumno=alumno_id)
        receptor = alumno.padre

        if receptor:
            sf = _mensaje_sender_field()
            rf = _mensaje_recipient_field()

            kwargs = {
                sf: request.user,
                rf: receptor,
                "asunto": asunto,
                "contenido": contenido,
                "school": active_school or getattr(alumno, "school", None),
            }
            if _has_model_field(Mensaje, "school_course") and getattr(alumno, "school_course", None) is not None:
                kwargs["school_course"] = getattr(alumno, "school_course", None)
            if getattr(alumno, "curso", None):
                kwargs["curso"] = getattr(alumno, "curso", None)

            msg = Mensaje.objects.create(**kwargs)
            try:
                contenido_corto = (contenido[:160] + "...") if len(contenido) > 160 else contenido
                url = "/mensajes"
                if hasattr(msg, "thread_id") and getattr(msg, "thread_id", None):
                    url = f"/mensajes/hilo/{getattr(msg, 'thread_id')}"
                actor_label = (request.user.get_full_name() or request.user.username or "Usuario").strip()
                titulo = f"{actor_label}: {asunto}" if asunto else f"Nuevo mensaje de {actor_label}"
                Notificacion.objects.create(
                    school=active_school or getattr(alumno, "school", None),
                    destinatario=receptor,
                    tipo="mensaje",
                    titulo=titulo,
                    descripcion=contenido_corto.strip() or None,
                    url=url,
                    leida=False,
                    meta={
                        "mensaje_id": getattr(msg, "id", None),
                        "thread_id": str(getattr(msg, "thread_id", "")) if hasattr(msg, "thread_id") else str(getattr(msg, "id", "")),
                        **_notification_course_meta(
                            alumno=alumno,
                            school_course=getattr(msg, "school_course", None),
                            course_code=getattr(alumno, "curso", "") if alumno else "",
                            school=active_school,
                        ),
                        "remitente_id": getattr(request.user, "id", None),
                        "alumno_id": getattr(alumno, "id", None) if alumno else None,
                    },
                )
            except Exception:
                pass
            return redirect('index')
        else:
            return HttpResponse("Este alumno no tiene padre asignado.", status=400)

    return render(request, 'calificaciones/enviar_mensaje.html', {
        'cursos': cursos_disponibles,
        'curso_seleccionado': curso_seleccionado,
        'curso_seleccionado_id': curso_seleccionado_id,
        'alumnos': alumnos
    })


@login_required
def enviar_comunicado(request):
    if not (_has_role(request, 'Profesores') or request.user.is_superuser):
        return HttpResponse("No tenÃ©s permiso.", status=403)

    active_school = get_request_school(request)
    cursos = _school_course_options_for_ui(school=active_school)
    if _has_role(request, "Profesores") and not request.user.is_superuser:
        assigned_refs = _profesor_assignment_refs(request.user, school=active_school)
        if assigned_refs:
            cursos = filter_course_options_by_refs(cursos, assigned_refs)

    if request.method == 'POST':
        selected_course = _resolve_request_course_selection(
            request,
            school=active_school,
            required=True,
        )
        if selected_course["error"]:
            return HttpResponse(selected_course["error"], status=400)
        curso = selected_course["course_code"]
        curso_id = selected_course["school_course_id"]
        if _has_role(request, "Profesores") and not request.user.is_superuser:
            assigned_refs = _profesor_assignment_refs(request.user, school=active_school)
            if assigned_refs and not course_ref_matches(
                assigned_refs,
                school_course_id=curso_id,
                course_code=curso,
            ):
                return HttpResponse("No tenÃ©s permiso para ese curso.", status=403)
        asunto = request.POST['asunto']
        contenido = request.POST['contenido']
        alumnos = scope_queryset_to_school(Alumno.objects.all(), active_school).filter(
            school_course_id=curso_id,
            padre__isnull=False,
        )

        sf = _mensaje_sender_field()
        rf = _mensaje_recipient_field()

        notifs = []
        for alumno in alumnos:
            kwargs = {
                sf: request.user,
                rf: alumno.padre,
                "asunto": asunto,
                "contenido": contenido,
                "school": active_school or getattr(alumno, "school", None),
            }
            if _has_model_field(Mensaje, "school_course") and getattr(alumno, "school_course", None) is not None:
                kwargs["school_course"] = getattr(alumno, "school_course", None)
            kwargs["curso"] = curso
            msg = Mensaje.objects.create(**kwargs)
            try:
                contenido_corto = (contenido[:160] + "...") if len(contenido) > 160 else contenido
                url = "/mensajes"
                if hasattr(msg, "thread_id") and getattr(msg, "thread_id", None):
                    url = f"/mensajes/hilo/{getattr(msg, 'thread_id')}"
                actor_label = (request.user.get_full_name() or request.user.username or "Usuario").strip()
                titulo = f"{actor_label}: {asunto}" if asunto else f"Nuevo mensaje de {actor_label}"
                notifs.append(
                    Notificacion(
                        school=active_school or getattr(alumno, "school", None),
                        destinatario=alumno.padre,
                        tipo="mensaje",
                        titulo=titulo,
                        descripcion=contenido_corto.strip() or None,
                        url=url,
                        leida=False,
                        meta={
                            "mensaje_id": getattr(msg, "id", None),
                            "thread_id": str(getattr(msg, "thread_id", "")) if hasattr(msg, "thread_id") else str(getattr(msg, "id", "")),
                            **_notification_course_meta(
                                alumno=alumno,
                                school_course=getattr(msg, "school_course", None),
                                course_code=curso,
                                school=active_school,
                            ),
                            "remitente_id": getattr(request.user, "id", None),
                            "alumno_id": getattr(alumno, "id", None),
                        },
                    )
                )
            except Exception:
                pass

        if notifs:
            try:
                Notificacion.objects.bulk_create(notifs)
            except Exception:
                pass

        return redirect('index')

    selected_course = _resolve_request_course_selection(
        request,
        school=active_school,
        required=False,
    )
    if selected_course["error"]:
        return HttpResponse(selected_course["error"], status=400)
    return render(request, 'calificaciones/enviar_comunicado.html', {
        'cursos': cursos,
        'curso_seleccionado_id': selected_course["school_course_id"],
    })

@login_required
def ver_mensajes(request):
    """
    Lista los mensajes recibidos por el usuario autenticado (padre/tutor).
    Evita usar campos inexistentes y ordena por 'fecha_envio' si existe.
    """
    if _has_role(request, 'Padres') or request.user.is_superuser:
        active_school = get_request_school(request)
        order_field = 'fecha_envio' if _has_model_field(Mensaje, 'fecha_envio') else 'id'

        rf = _mensaje_recipient_field()
        mensajes = scope_queryset_to_school(
            Mensaje.objects.filter(**{rf: request.user}),
            active_school,
        ).order_by(f'-{order_field}')
        select_fields = [_mensaje_sender_field(), _mensaje_recipient_field()]
        if _has_model_field(Mensaje, "school_course"):
            select_fields.append("school_course")
        mensajes = mensajes.select_related(*select_fields)

        return render(request, 'calificaciones/ver_mensajes.html', {'mensajes': mensajes})
    else:
        return HttpResponse("No tienes permiso para ver mensajes.", status=403)


# =========================================================
#  BoletÃ­n / Historial
# =========================================================
@login_required
def generar_boletin_pdf(request, alumno_id):
    active_school = get_request_school(request)
    alumno = get_object_or_404(
        scope_queryset_to_school(Alumno.objects.select_related("school", "school_course"), active_school),
        id_alumno=alumno_id,
    )
    if not _can_access_alumno_data(request, alumno):
        return HttpResponse("No tenÃ©s permiso para ver este boletÃ­n.", status=403)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="boletin_{alumno.nombre}.pdf'
    p = canvas.Canvas(response)
    p.drawString(100, 800, f"BoletÃ­n de {alumno.nombre}")
    y = 750
    notas = scope_queryset_to_school(Nota.objects.filter(alumno=alumno), active_school).order_by('cuatrimestre')
    for nota in notas:
        p.drawString(100, y, f"{nota.materia} - Cuatrimestre {nota.cuatrimestre}: {nota.calificacion}")
        y -= 20
    p.showPage()
    p.save()
    return response


@login_required
def historial_notas_profesor(request, alumno_id):
    if not (_has_role(request, 'Profesores') or request.user.is_superuser):
        return HttpResponse("No tenÃ©s permiso para ver esto.", status=403)

    active_school = get_request_school(request)
    alumno = get_object_or_404(scope_queryset_to_school(Alumno.objects.all(), active_school), id_alumno=alumno_id)
    viewer_groups = set(_effective_groups(request))
    if "Profesores" in viewer_groups and not request.user.is_superuser:
        if not _profesor_can_access_alumno(request.user, alumno):
            return HttpResponse("No tenÃ©s permiso para ese curso.", status=403)
    notas_base_qs = scope_queryset_to_school(Nota.objects.filter(alumno=alumno), active_school)
    materias = set(notas_base_qs.values_list('materia', flat=True))
    materia_seleccionada = request.GET.get('materia')
    notas = []

    if materia_seleccionada:
        notas = notas_base_qs.filter(materia=materia_seleccionada).order_by('cuatrimestre')

    return render(request, 'calificaciones/historial_notas.html', {
        'alumno': alumno,
        'materias': materias,
        'materia_seleccionada': materia_seleccionada,
        'notas': notas
    })


@login_required
def historial_notas_padre(request):
    if not (_has_role(request, 'Padres') or request.user.is_superuser):
        return HttpResponse("No tenÃ©s permiso para ver esto.", status=403)

    active_school = get_request_school(request)
    alumnos_qs = scope_queryset_to_school(
        Alumno.objects.select_related("school_course"),
        active_school,
    )
    alumnos = alumnos_qs.filter(padre=request.user)
    if not alumnos.exists() and _get_preview_role(request):
        a0 = alumnos_qs.filter(padre__isnull=False).order_by('padre_id').first()
        if a0 and a0.padre_id:
            alumnos = alumnos_qs.filter(padre_id=a0.padre_id)
    alumno = alumnos.first()

    notas_base_qs = scope_queryset_to_school(Nota.objects.filter(alumno=alumno), active_school) if alumno else Nota.objects.none()
    materias = set(notas_base_qs.values_list('materia', flat=True)) if alumno else set()
    materia_seleccionada = request.GET.get('materia')
    notas = []

    if materia_seleccionada and alumno:
        notas = notas_base_qs.filter(materia=materia_seleccionada).order_by('cuatrimestre')

    return render(request, 'calificaciones/historial_notas.html', {
        'alumno': alumno,
        'materias': materias,
        'materia_seleccionada': materia_seleccionada,
        'notas': notas
    })


# =========================================================
#  Vistas HTML calendario
# =========================================================
@login_required
def calendario_view(request):
    form = EventoForm(school=get_request_school(request))
    return render(request, 'calificaciones/calendario.html', {'form': form})


@login_required
def crear_evento(request):
    if not (_has_role(request, 'Profesores') or request.user.is_superuser):
        return HttpResponse("No tenÃ©s permiso para crear eventos.", status=403)

    active_school = get_request_school(request)
    assigned_refs = []
    if _has_role(request, "Profesores") and not request.user.is_superuser:
        assigned_refs = _profesor_assignment_refs(request.user, school=active_school)

    if request.method == 'POST':
        form = EventoForm(request.POST, school=active_school)
        if assigned_refs:
            selected_course = _resolve_request_course_selection(
                request,
                school=active_school,
                required=True,
            )
            if selected_course["error"]:
                return JsonResponse({"detail": selected_course["error"]}, status=400)
            if not course_ref_matches(
                assigned_refs,
                school_course_id=selected_course["school_course_id"],
                course_code=selected_course["course_code"],
            ):
                return JsonResponse({"detail": "No autorizado para ese curso."}, status=403)
        if form.is_valid():
            evento = form.save(commit=False)
            evento.creado_por = request.user
            evento.school = active_school
            evento.save()
            try:
                from .api_eventos import _notify_evento_creado
                _notify_evento_creado(request, evento)
            except Exception:
                pass
            return JsonResponse({"id": evento.id})
        else:
            return JsonResponse({"errors": form.errors}, status=400)

    return JsonResponse({"detail": "Metodo no permitido"}, status=405)


@login_required
def editar_evento(request, evento_id):
    active_school = get_request_school(request)
    evento = get_object_or_404(scope_queryset_to_school(Evento.objects.all(), active_school), id=evento_id)
    evento_owner = getattr(evento, "creado_por", None)

    if not (request.user == evento_owner or request.user.is_superuser):
        return HttpResponse("No tenÃ©s permiso para editar este evento.", status=403)

    if request.method == 'POST':
        form = EventoForm(request.POST, instance=evento, school=active_school)
        if _has_role(request, "Profesores") and not request.user.is_superuser:
            assigned_refs = _profesor_assignment_refs(request.user, school=active_school)
            if assigned_refs:
                selected_course = _resolve_request_course_selection(
                    request,
                    school=active_school,
                    required=True,
                )
                if selected_course["error"]:
                    return JsonResponse({"detail": selected_course["error"]}, status=400)
                if not course_ref_matches(
                    assigned_refs,
                    school_course_id=selected_course["school_course_id"],
                    course_code=selected_course["course_code"],
                ):
                    return JsonResponse({"detail": "No autorizado para ese curso."}, status=403)
        if form.is_valid():
            evento = form.save()
            return JsonResponse({"id": evento.id})
        else:
            return JsonResponse({"errors": form.errors}, status=400)
    else:
        form = EventoForm(instance=evento, school=active_school)
        return render(request, 'calificaciones/parcial_editar_evento.html', {'form': form, 'evento': evento})


@login_required
def eliminar_evento(request, evento_id):
    active_school = get_request_school(request)
    evento = get_object_or_404(scope_queryset_to_school(Evento.objects.all(), active_school), id=evento_id)
    evento_owner = getattr(evento, "creado_por", None)

    if not (request.user == evento_owner or request.user.is_superuser):
        return HttpResponse("No tenÃ©s permiso para eliminar este evento.", status=403)

    if request.method == 'POST':
        evento.delete()
        return redirect('calendario')

    return render(request, 'calificaciones/confirmar_eliminar_evento.html', {'evento': evento})


# =========================================================
#  Asistencias / Perfiles especÃ­ficos
# =========================================================
@login_required
def pasar_asistencia(request):
    usuario = request.user
    active_school = get_request_school(request)
    alumnos = []
    curso_id = None
    curso_code = None
    school_course_name = None

    if usuario.is_superuser:
        cursos = _school_course_options_for_ui(school=active_school)
        selected_course = _resolve_request_course_selection(
            request,
            school=active_school,
            required=False,
        )
        if selected_course["error"]:
            return render(request, 'calificaciones/error.html', {'mensaje': selected_course["error"]}, status=400)
        curso_id = selected_course["school_course_id"]
        curso_code = selected_course["course_code"]
        if curso_code:
            school_course_name = get_course_label(curso_code, school=active_school)
    else:
        allowed_refs = _preceptor_assignment_refs(usuario, school=active_school)
        if not allowed_refs:
            return render(request, 'calificaciones/error.html', {'mensaje': 'No tenÃ©s un curso asignado como preceptor.'})
        cursos = filter_course_options_by_refs(_school_course_options_for_ui(school=active_school), allowed_refs)
        selected_course = _resolve_request_course_selection(
            request,
            school=active_school,
            required=False,
        )
        if selected_course["error"]:
            return render(request, 'calificaciones/error.html', {'mensaje': selected_course["error"]}, status=400)
        if (selected_course["school_course_id"] or selected_course["course_code"]) and not course_ref_matches(
            allowed_refs,
            school_course_id=selected_course["school_course_id"],
            course_code=selected_course["course_code"],
        ):
            return render(request, 'calificaciones/error.html', {'mensaje': 'No tenÃ©s permiso para ese curso.'})
        selected_option = None
        if selected_course["school_course_id"]:
            selected_option = next(
                (option for option in cursos if option.get("school_course_id") == selected_course["school_course_id"]),
                None,
            )
        if selected_option is None and selected_course["course_code"]:
            selected_option = next(
                (option for option in cursos if option.get("code") == selected_course["course_code"]),
                None,
            )
        if selected_option is None and cursos:
            selected_option = cursos[0]

        if selected_option is not None:
            curso_id = selected_option.get("school_course_id")
            curso_code = selected_option.get("code")
            school_course_name = selected_option.get("nombre") or get_course_label(curso_code, school=active_school)

    if curso_code:
        alumnos = (
            _alumnos_por_curso_qs(curso_code, school=active_school)
            .select_related("school", "school_course", "padre", "usuario")
            .order_by('nombre')
        )

    if request.method == 'POST':
        fecha_actual = date.today()
        asistencia_objs = []
        ausentes_ids = []
        for alumno in alumnos:
            presente = request.POST.get(f'asistencia_{alumno.id}') == 'on'
            asistencia_objs.append(Asistencia(
                school=active_school or getattr(alumno, "school", None),
                alumno=alumno,
                fecha=fecha_actual,
                presente=presente
            ))
            if not presente:
                ausentes_ids.append(alumno.id)

        Asistencia.objects.filter(alumno__in=alumnos, fecha=fecha_actual).delete()
        Asistencia.objects.bulk_create(asistencia_objs)

        # Notificar inasistencias a padres/alumnos
        try:
            for alumno in alumnos:
                if alumno.id not in ausentes_ids:
                    continue
                destinatarios = _resolver_destinatarios_notif(alumno)
                if not destinatarios:
                    continue
                alumno_nombre = (f"{getattr(alumno, 'apellido', '')} {getattr(alumno, 'nombre', '')}").strip()
                if not alumno_nombre:
                    alumno_nombre = getattr(alumno, "nombre", "") or str(getattr(alumno, "id_alumno", "")) or "Alumno"
                titulo = f"Inasistencia registrada: {alumno_nombre}"
                course_name = _notification_course_name(alumno=alumno)
                descripcion = f"Alumno: {alumno_nombre} Â· Curso: {course_name or 's/d'} Â· Fecha: {fecha_actual.isoformat()}"
                for dest in destinatarios:
                    Notificacion.objects.create(
                        school=active_school or getattr(alumno, "school", None),
                        destinatario=dest,
                        tipo="inasistencia",
                        titulo=titulo,
                        descripcion=descripcion,
                        url=f"/alumnos/{getattr(alumno, 'id', '')}/?tab=asistencias",
                        leida=False,
                        meta={
                            "alumno_id": getattr(alumno, "id", None),
                            "alumno_legajo": getattr(alumno, "id_alumno", None),
                            **_notification_course_meta(alumno=alumno, school=active_school),
                            "fecha": fecha_actual.isoformat(),
                            "tipo_asistencia": "clases",
                        },
                    )
        except Exception:
            pass

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({"registradas": len(asistencia_objs)})
        return redirect('index')

    return render(request, 'calificaciones/pasar_asistencia.html', {
        'alumnos': alumnos,
        'curso_id': curso_id,
        'curso_code': curso_code,
        'school_course_name': school_course_name,
        'cursos': cursos
    })


@login_required
def perfil_alumno(request, alumno_id):
    active_school = get_request_school(request)
    alumno = get_object_or_404(
        scope_queryset_to_school(
            Alumno.objects.select_related("school", "school_course", "padre", "usuario"),
            active_school,
        ),
        id_alumno=alumno_id,
    )
    viewer_groups = set(_effective_groups(request))

    is_padre = (request.user == alumno.padre)
    is_prof_ok = ("Profesores" in viewer_groups) and _profesor_can_access_alumno(request.user, alumno)
    is_prof_or_super = (request.user.is_superuser or is_prof_ok)
    # Alumno propio (mismo criterio que en endpoints API)
    is_alumno_mismo = getattr(alumno, "usuario_id", None) == request.user.id
    if not is_alumno_mismo and "Alumnos" in viewer_groups:
        try:
            r = resolve_alumno_for_user(request.user, school=active_school)
            if r.alumno and r.alumno.id == alumno.id:
                is_alumno_mismo = True
        except Exception:
            pass

    # âœ… NUEVO: permitir preceptor si el curso coincide
    is_preceptor_ok = (
        ("Directivos" in viewer_groups)
        or (("Preceptores" in viewer_groups) and _preceptor_can_access_alumno(request.user, alumno))
    )

    if not (is_padre or is_prof_or_super or is_alumno_mismo or is_preceptor_ok):
        return HttpResponse("No tenÃ©s permiso para ver este perfil.", status=403)

    # âœ… NUEVO: contamos ausentes como 1 y "tarde" como 0.5
    asistencias_base_qs = scope_queryset_to_school(Asistencia.objects.filter(alumno=alumno), active_school)
    asistencias_irregulares = asistencias_base_qs.filter(
        Q(presente=False) | Q(tarde=True)
    ).order_by('-fecha')

    resumen_asist = asistencias_base_qs.aggregate(
        ausentes=Count("id", filter=Q(presente=False)),
        tardes=Count("id", filter=Q(presente=True, tarde=True)),
    )
    ausentes_cnt = int(resumen_asist.get("ausentes") or 0)
    tarde_cnt = int(resumen_asist.get("tardes") or 0)
    faltas_equivalentes = ausentes_cnt + (tarde_cnt * 0.5)

    return render(request, 'calificaciones/perfil_alumno.html', {
        'alumno': alumno,
        'asistencias_irregulares': asistencias_irregulares,
        'faltas_equivalentes': faltas_equivalentes,
    })


# =========================================================
#  Endpoint JSON minimal legado
# =========================================================
@login_required
def mi_perfil(request):
    """
    VersiÃ³n minimal del perfil del usuario autenticado.
    """
    user = request.user
    viewer_groups = set(_effective_groups(request))
    active_school = get_request_school(request)
    groups = _effective_groups(request)

    # Alumno propio (resolucion tolerante)
    r = resolve_alumno_for_user(user, school=active_school)
    alumno_vinculado = r.alumno
    assigned_school_courses = _profile_assigned_school_courses(
        user=user,
        groups=groups,
        school=active_school,
    )

    data = {
        "username": user.username,
        "email": user.email,
        "groups": groups,
        "rol": _rol_principal(user),
        "is_superuser": user.is_superuser,
        "school": school_to_dict(active_school),
        "available_schools": get_available_school_dicts_for_user(user, active_school=active_school),
        "assigned_school_courses": assigned_school_courses,
    }

    if alumno_vinculado:
        data["alumno"] = _alumno_to_dict(alumno_vinculado)

    return JsonResponse(data)


# =========================================================
#  Logout de sesiÃ³n (complementa blacklist de JWT)
# =========================================================
@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def auth_logout(request):
    """
    Cierra la sesiÃ³n de Django si la hubiera (cookie sessionid) y limpia cookies.
    Para JWT, complementamos con /api/token/blacklist/ desde el front.
    """
    try:
        if request.user.is_authenticated:
            dj_logout(request)
    except Exception:
        pass
    resp = HttpResponse(status=204)
    # Limpieza defensiva de cookies tÃ­picas
    resp.delete_cookie("sessionid")
    resp.delete_cookie("csrftoken")
    return clear_auth_cookies(resp)


# =========================================================
#  Cambiar contraseÃ±a (autenticado)
# =========================================================
@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
@throttle_classes([UserRateThrottle])
def auth_change_password(request):
    user = request.user
    data = request.data or {}

    current = (data.get("current_password") or data.get("password_actual") or "").strip()
    new = (data.get("new_password") or data.get("password_nueva") or "").strip()

    if not current or not new:
        return Response({"detail": "CompletÃ¡ la contraseÃ±a actual y la nueva."}, status=400)

    if not user.check_password(current):
        return Response({"detail": "La contraseÃ±a actual no coincide."}, status=400)

    try:
        validate_password(new, user=user)
    except ValidationError as exc:
        return Response({"detail": list(exc.messages)}, status=400)

    user.set_password(new)
    user.save(update_fields=["password"])

    # Revocar refresh tokens existentes si blacklist estÃ¡ habilitado
    try:
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
        tokens = OutstandingToken.objects.filter(user=user)
        for tok in tokens:
            BlacklistedToken.objects.get_or_create(token=tok)
    except Exception:
        pass

    # Mantener la sesiÃ³n de Django si estuviera usando cookies
    try:
        update_session_auth_hash(request, user)
    except Exception:
        pass

    return Response({"detail": "ContraseÃ±a actualizada."})


# =========================================================
#  âœ… NUEVO: contador de no leÃ­dos para el badge de la topbar
# =========================================================
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mensajes_unread_count(request):
    user = request.user
    inbox_qs = _mensajes_inbox_qs(user, school=get_request_school(request))
    count = _mensajes_unread_count_from_qs(inbox_qs)
    return Response({"count": count})

