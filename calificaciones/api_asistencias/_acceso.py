# calificaciones/api_asistencias/_acceso.py
"""
Helpers de roles y permisos para la API de asistencias.
"""
from __future__ import annotations

from ..models import Alumno
from ..user_groups import user_in_groups


def _user_in_group(user, *names: str) -> bool:
    """True si el usuario pertenece a alguno de los grupos indicados."""
    return user_in_groups(user, *names)


def _is_directivo_user(user) -> bool:
    return _user_in_group(user, "Directivos", "Directivo")


def _is_preceptor_user(user) -> bool:
    return _user_in_group(user, "Preceptores", "Preceptor")


def _is_profesor_user(user) -> bool:
    return _user_in_group(user, "Profesores", "Profesor")


def _can_justify(user) -> bool:
    """Preceptores, directivos y superuser pueden justificar."""
    if getattr(user, "is_superuser", False) or _is_directivo_user(user):
        return True
    return _is_preceptor_user(user)


def _can_sign_asistencia(user, alumno: Alumno) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    return getattr(alumno, "padre_id", None) == getattr(user, "id", None)


def _can_edit_asistencia_detalle(user, alumno: Alumno) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    if _is_directivo_user(user):
        return True
    return _is_preceptor_user(user)
