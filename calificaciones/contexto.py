from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from django.contrib.auth.models import User
from django.core.cache import cache

from .models import Alumno
from .schools import get_unique_alumno_by_legajo, scope_queryset_to_school


@dataclass(frozen=True)
class AlumnoResolution:
    alumno: Optional[Alumno]
    method: str
    candidates: int = 0


ALUMNO_RESOLUTION_CACHE_TTL = 120


def _alumno_resolution_cache_key(user, school_id) -> str:
    user_id = getattr(user, "id", None)
    username = str(getattr(user, "username", "") or "").strip().lower() or "anon"
    return f"alumno_resolution:user:{user_id or 'x'}:{username}:school:{school_id or 'none'}"


def alumno_to_dict(a: Optional[Alumno]) -> Optional[Dict[str, Any]]:
    if not a:
        return None
    school_course = getattr(a, "school_course", None)
    return {
        "id": a.id,
        "id_alumno": getattr(a, "id_alumno", None),
        "nombre": a.nombre,
        "school_course_id": getattr(a, "school_course_id", None),
        "school_course_name": getattr(school_course, "name", None) or getattr(school_course, "code", None) or a.curso,
        "school_id": getattr(a, "school_id", None),
        "padre_id": a.padre_id,
        "usuario_id": getattr(a, "usuario_id", None),
    }


def resolve_alumno_for_user(user: User, school=None) -> AlumnoResolution:
    """
    Resuelve el "alumno propio" para un User autenticado.

    Orden de resolucion:
    1) Alumno.usuario == user
    2) Alumno.id_alumno == user.username
    3) Alumno.padre == user, solo si hay 1 hijo
    """

    school_id = getattr(school, "id", None)
    cached_by_school = getattr(user, "_cached_alumno_resolution_by_school", None)
    if isinstance(cached_by_school, dict) and school_id in cached_by_school:
        return cached_by_school[school_id]

    cache_key = _alumno_resolution_cache_key(user, school_id)
    try:
        cached = cache.get(cache_key)
        if cached is not None:
            alumno = None
            alumno_id = cached.get("alumno_id")
            if alumno_id is not None:
                alumno = scope_queryset_to_school(
                    Alumno.objects.select_related("school", "school_course"),
                    school,
                ).filter(id=alumno_id).first()
            resolution = AlumnoResolution(
                alumno=alumno,
                method=str(cached.get("method") or "cached"),
                candidates=int(cached.get("candidates") or 0),
            )
            try:
                if not isinstance(cached_by_school, dict):
                    cached_by_school = {}
                cached_by_school[school_id] = resolution
                setattr(user, "_cached_alumno_resolution_by_school", cached_by_school)
            except Exception:
                pass
            return resolution
    except Exception:
        pass

    base_qs = scope_queryset_to_school(
        Alumno.objects.select_related("school", "school_course"),
        school,
    )
    resolution = AlumnoResolution(None, "no_match", 0)

    try:
        a = base_qs.filter(usuario=user).first()
        if a is not None:
            resolution = AlumnoResolution(a, "usuario_link", 1)
    except Exception:
        pass

    if resolution.alumno is None:
        try:
            uname = (getattr(user, "username", "") or "").strip()
            if uname:
                a = get_unique_alumno_by_legajo(uname, school=school)
                if a is not None:
                    resolution = AlumnoResolution(a, "username_as_legajo", 1)
        except Exception:
            pass

    if resolution.alumno is None:
        try:
            hijos = list(base_qs.filter(padre=user)[:2])
            if len(hijos) == 1:
                resolution = AlumnoResolution(hijos[0], "padre_unico_hijo", 1)
            elif len(hijos) > 1:
                resolution = AlumnoResolution(None, "padre_multiples_hijos", len(hijos))
        except Exception:
            pass

    try:
        if not isinstance(cached_by_school, dict):
            cached_by_school = {}
        cached_by_school[school_id] = resolution
        setattr(user, "_cached_alumno_resolution_by_school", cached_by_school)
    except Exception:
        pass

    try:
        cache.set(
            cache_key,
            {
                "alumno_id": getattr(getattr(resolution, "alumno", None), "id", None),
                "method": resolution.method,
                "candidates": resolution.candidates,
            },
            ALUMNO_RESOLUTION_CACHE_TTL,
        )
    except Exception:
        pass

    return resolution


def build_context_for_user(user: User, groups: List[str], school=None) -> Dict[str, Any]:
    """
    Construye un contexto estable para el front:
    - alumno_propio: para rol Alumnos (o cuando se puede inferir univocamente)
    """
    ctx: Dict[str, Any] = {}

    if "Alumnos" in groups:
        r = resolve_alumno_for_user(user, school=school)
        ctx["alumno"] = alumno_to_dict(r.alumno)

    return ctx
