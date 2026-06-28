# calificaciones/api_mensajes_alumno/_helpers.py
from __future__ import annotations

from typing import Optional

from django.contrib.auth.models import User
from django.core.exceptions import FieldDoesNotExist

from ..course_access import filter_assignments_for_course
from ..models import Alumno, Mensaje, resolve_school_course_for_value
from ..schools import get_request_school, get_unique_alumno_by_legajo, scope_queryset_to_school
from ..user_groups import get_first_user_group_name, get_user_group_names
from ..utils_cursos import resolve_course_reference

try:
    from ..models_preceptores import PreceptorCurso, ProfesorCurso
except Exception:
    PreceptorCurso = None
    ProfesorCurso = None


# =========================================================
# Helpers
# =========================================================
PROF_GROUPS = ["Profesor", "Profesores", "Docente", "Docentes"]
PREC_GROUPS = ["Preceptor", "Preceptores"]


def _has_field(model, field_name: str) -> bool:
    try:
        model._meta.get_field(field_name)
        return True
    except FieldDoesNotExist:
        return False


def _sender_field() -> str:
    """Compat: Mensaje.remitente (nuevo) vs Mensaje.emisor (viejo)."""
    return "remitente" if _has_field(Mensaje, "remitente") else "emisor"


def _recipient_field() -> str:
    """Compat: Mensaje.destinatario (nuevo) vs Mensaje.receptor (viejo)."""
    return "destinatario" if _has_field(Mensaje, "destinatario") else "receptor"


def _course_code_from_context(*, alumno: Alumno | None = None, school_course=None, curso: str = "") -> str:
    alumno_school_course = getattr(alumno, "school_course", None) if alumno is not None else None
    return str(
        getattr(school_course, "code", None)
        or getattr(alumno_school_course, "code", None)
        or getattr(alumno, "curso", None)
        or curso
        or ""
    ).strip()


def _course_name(alumno: Alumno | None = None, *, school_course=None, curso: str = "") -> str:
    school_course = school_course or getattr(alumno, "school_course", None)
    return (
        getattr(school_course, "name", None)
        or getattr(school_course, "code", None)
        or getattr(alumno, "curso", None)
        or curso
        or ""
    )


def _course_context(*, alumno: Alumno | None = None, school_course=None, curso: str = "", school=None):
    school_course = school_course or (getattr(alumno, "school_course", None) if alumno is not None else None)
    course_code = _course_code_from_context(alumno=alumno, school_course=school_course, curso=curso)
    if school_course is None and course_code and school is not None:
        school_course = resolve_school_course_for_value(school=school, curso=course_code)
    return {
        "school_course": school_course,
        "school_course_id": getattr(school_course, "id", None),
        "school_course_name": _course_name(alumno, school_course=school_course, curso=course_code),
    }


def _user_to_dict(u: User, grupo_hint: str = ""):
    nombre = (u.get_full_name() or u.username or f"usuario-{u.id}").strip()
    return {
        "id": u.id,
        "nombre": nombre,
        "username": u.username,
        "grupo": grupo_hint or get_first_user_group_name(u, ""),
    }


def _infer_alumno_for_user(user: User, school=None) -> Optional[Alumno]:
    """Intenta inferir el Alumno asociado a este user (usuario o padre)."""
    school_id = getattr(school, "id", None) or 0
    cached = getattr(user, "_cached_inferred_alumno_by_school", None)
    if isinstance(cached, dict) and school_id in cached:
        return cached[school_id]

    qs = scope_queryset_to_school(
        Alumno.objects.select_related("school", "school_course"),
        school,
    )

    alumno = None

    if alumno is None:
        try:
            alumno = qs.filter(usuario=user).first() if _has_field(Alumno, "usuario") else None
        except Exception:
            alumno = None

    if alumno is None:
        try:
            username = (getattr(user, "username", "") or "").strip()
            if username:
                alumno = get_unique_alumno_by_legajo(username, school=school)
        except Exception:
            alumno = None

    if alumno is None:
        try:
            alumno = qs.filter(padre=user).order_by("id").first()
        except Exception:
            alumno = None

    if alumno is None:
        try:
            full = (user.get_full_name() or "").strip()
            if full:
                alumno = qs.filter(nombre__iexact=full).order_by("id").first()
        except Exception:
            alumno = None

    try:
        if not isinstance(cached, dict):
            cached = {}
        cached[school_id] = alumno
        setattr(user, "_cached_inferred_alumno_by_school", cached)
    except Exception:
        pass

    return alumno


def _school_assignment_qs(model, school=None, school_course=None, curso: str = ""):
    if model is None:
        return None
    qs = scope_queryset_to_school(model.objects.all(), school)
    school_course_id = getattr(school_course, "id", None)
    course_code = _course_code_from_context(school_course=school_course, curso=curso)
    if school_course_id is not None or course_code:
        qs = filter_assignments_for_course(
            qs,
            school=school,
            school_course_id=school_course_id,
            course_code=course_code,
        )
    return qs


def _school_has_assignment_data(school=None) -> bool:
    for model in (ProfesorCurso, PreceptorCurso):
        qs = _school_assignment_qs(model, school=school)
        if qs is None:
            continue
        try:
            if qs.exists():
                return True
        except Exception:
            continue
    return False


def _allowed_docentes_qs(*, school=None, school_course=None, curso: str = "", alumno: Optional[Alumno] = None):
    """
    Usa asignaciones por school/curso cuando existen.
    Si todavía no hay asignaciones cargadas para ese school, cae al listado general.
    """
    base = User.objects.filter(is_active=True, groups__name__in=(PROF_GROUPS + PREC_GROUPS)).distinct()
    user_ids = set()

    qs_prof = _school_assignment_qs(ProfesorCurso, school=school, school_course=school_course, curso=curso)
    if qs_prof is not None:
        if alumno is not None:
            qs_prof = filter_assignments_for_course(qs_prof, obj=alumno, school=school)
        user_ids.update(uid for uid in qs_prof.values_list("profesor_id", flat=True) if uid is not None)

    qs_prec = _school_assignment_qs(PreceptorCurso, school=school, school_course=school_course, curso=curso)
    if qs_prec is not None:
        if alumno is not None:
            qs_prec = filter_assignments_for_course(qs_prec, obj=alumno, school=school)
        user_ids.update(uid for uid in qs_prec.values_list("preceptor_id", flat=True) if uid is not None)

    if user_ids:
        return base.filter(id__in=user_ids)
    if not _school_has_assignment_data(school=school):
        return base
    return base.none()


def _allowed_docentes_list(*, school=None, school_course=None, curso: str = "", alumno: Optional[Alumno] = None):
    return list(
        _allowed_docentes_qs(
            school=school,
            school_course=school_course,
            curso=curso,
            alumno=alumno,
        ).prefetch_related("groups")
    )
