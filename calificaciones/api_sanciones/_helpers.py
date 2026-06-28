# calificaciones/api_sanciones/_helpers.py
from __future__ import annotations

import json
from typing import Any, Optional

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt

from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    parser_classes,
)
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from ..jwt_auth import CookieJWTAuthentication as JWTAuthentication

from ..contexto import resolve_alumno_for_user
from ..course_access import build_course_membership_q, course_ref_matches, get_assignment_course_refs
from ..models import Alumno, Sancion, Notificacion, resolve_school_course_for_value
from ..schools import get_request_school, scope_queryset_to_school
from ..serializers import SancionPublicSerializer
from ..signatures import claim_signature
from ..user_groups import get_user_group_names, get_user_group_names_lower
from ..utils_cursos import resolve_course_reference
from ..utils_pagination import paginate_queryset
# ✅ FIX CLAVE: antes no existía User y las notificaciones fallaban silenciosamente
User = get_user_model()

try:
    from ..models_preceptores import PreceptorCurso, ProfesorCurso  # type: ignore
except Exception:
    PreceptorCurso = None
    ProfesorCurso = None


# =========================================================
# Helpers
# =========================================================
def _alumno_base_qs(school=None):
    return scope_queryset_to_school(
        Alumno.objects.select_related("school", "school_course", "padre", "usuario"),
        school,
    )


def _resolver_alumno_id(valor: Any, school=None) -> Optional[Alumno]:
    """
    Acepta PK (int), id_alumno (legajo) o string convertible.

    FIX SOLIDO:
    - Si viene numérico, probamos primero como PK.
    - Si ese PK no existe, caemos a id_alumno (legajo).
    Esto evita que un legajo numérico se interprete como PK incorrecto.
    """
    if valor is None:
        return None

    try:
        sv = str(valor).strip()
        if not sv:
            return None
        alumnos_qs = _alumno_base_qs(school)

        # 1) Intentar PK si es dígito
        if sv.isdigit():
            try:
                return alumnos_qs.get(pk=int(sv))
            except Alumno.DoesNotExist:
                pass

        # 2) Intentar por legajo/id_alumno (case-insensitive)
        return alumnos_qs.filter(id_alumno__iexact=sv).first()

    except Exception:
        return None


def _preceptor_course_refs(user, school=None):
    if PreceptorCurso is None:
        return []

    school_id = getattr(school, "id", None) or 0
    cache_attr = "_cached_sanciones_preceptor_refs_by_school"
    cached = getattr(user, cache_attr, None)
    if isinstance(cached, dict) and school_id in cached:
        return list(cached[school_id])

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
    return refs


def _profesor_course_refs(user, school=None):
    if ProfesorCurso is None:
        return []

    school_id = getattr(school, "id", None) or 0
    cache_attr = "_cached_sanciones_profesor_refs_by_school"
    cached = getattr(user, cache_attr, None)
    if isinstance(cached, dict) and school_id in cached:
        return list(cached[school_id])

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
    return refs


def _user_label(user) -> str:
    try:
        full = (user.get_full_name() or "").strip()
        if full:
            return full
        return (getattr(user, "username", "") or "").strip()
    except Exception:
        return ""


def _course_name(alumno: Alumno | None) -> str:
    school_course = getattr(alumno, "school_course", None) if alumno is not None else None
    return (
        getattr(school_course, "name", None)
        or getattr(school_course, "code", None)
        or getattr(alumno, "curso", "")
        or ""
    )


def _course_meta(alumno: Alumno | None) -> dict[str, Any]:
    return {
        "school_course_id": getattr(alumno, "school_course_id", None) if alumno is not None else None,
        "school_course_name": _course_name(alumno),
    }


def _filter_sanciones_por_curso(qs, curso: str, *, school=None, school_course=None):
    curso = str(curso or "").strip()
    resolved_school_course = school_course
    if not curso and resolved_school_course is not None:
        curso = str(getattr(resolved_school_course, "code", "") or "").strip()
    if not curso and resolved_school_course is None:
        return qs

    if resolved_school_course is None and school is not None:
        resolved_school_course = resolve_school_course_for_value(school=school, curso=curso)
    course_q = build_course_membership_q(
        school_course_id=getattr(resolved_school_course, "id", None),
        course_code=curso,
        school_course_field="alumno__school_course",
        code_field="alumno__curso",
    )
    if course_q is None:
        return qs.none()
    return qs.filter(course_q)


def _is_docente_o_preceptor(user) -> bool:
    try:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True
        groups = get_user_group_names_lower(user)
        joined = " ".join(groups)
        return ("preceptor" in joined) or ("profesor" in joined) or ("docente" in joined) or ("directivo" in joined)
    except Exception:
        return False


def _is_directivo_user(user) -> bool:
    try:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        groups = set(get_user_group_names(user))
        return "Directivos" in groups or "Directivo" in groups
    except Exception:
        return False


def _preceptor_can_access_alumno(user, alumno: Alumno) -> bool:
    try:
        refs = _preceptor_course_refs(user, school=getattr(alumno, "school", None))
        return course_ref_matches(refs, obj=alumno)
    except Exception:
        return False


def _profesor_can_access_alumno(user, alumno: Alumno) -> bool:
    try:
        refs = _profesor_course_refs(user, school=getattr(alumno, "school", None))
        return course_ref_matches(refs, obj=alumno)
    except Exception:
        return False


def _authorize_staff_for_alumno(user, alumno: Alumno) -> bool:
    try:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False) or _is_directivo_user(user):
            return True
        groups = set(get_user_group_names_lower(user))
        joined = " ".join(groups)
        if "preceptor" in joined:
            return _preceptor_can_access_alumno(user, alumno)
        if ("profesor" in joined) or ("docente" in joined):
            return _profesor_can_access_alumno(user, alumno)
    except Exception:
        return False
    return False


def _authorize_padre_or_admin(user, alumno: Alumno) -> bool:
    try:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True
        return getattr(alumno, "padre_id", None) == getattr(user, "id", None)
    except Exception:
        return False


def _authorize_reader_for_alumno(user, alumno: Alumno) -> bool:
    if _authorize_padre_or_admin(user, alumno):
        return True
    if _authorize_staff_for_alumno(user, alumno):
        return True
    try:
        resolved = resolve_alumno_for_user(user, school=getattr(alumno, "school", None))
        return bool(resolved.alumno and resolved.alumno.id == alumno.id)
    except Exception:
        return False


def _alumno_fullname(a: Alumno) -> str:
    nm = (getattr(a, "nombre", "") or "").strip()
    # Fallback defensivo por si apellido no existe o viene vacío
    ap = (getattr(a, "apellido", "") or "").strip()
    full = (f"{ap}, {nm}").strip(", ").strip()
    return full or nm or str(getattr(a, "id_alumno", "")) or "Alumno"


def _get_payload(request) -> dict:
    """
    Devuelve payload como dict, tolerante a JSON / form-data.
    """
    try:
        if hasattr(request, "data"):
            # request.data puede ser QueryDict
            if isinstance(request.data, dict):
                return dict(request.data)
            return request.data
    except Exception:
        pass

    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return {}
