# calificaciones/contexto.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple

from django.contrib.auth.models import User

from .models import Alumno


@dataclass(frozen=True)
class AlumnoResolution:
    alumno: Optional[Alumno]
    method: str
    candidates: int = 0


def alumno_to_dict(a: Optional[Alumno]) -> Optional[Dict[str, Any]]:
    if not a:
        return None
    return {
        "id": a.id,
        "id_alumno": getattr(a, "id_alumno", None),
        "nombre": a.nombre,
        "curso": a.curso,
        "padre_id": a.padre_id,
        "usuario_id": getattr(a, "usuario_id", None),
    }


def resolve_alumno_for_user(user: User) -> AlumnoResolution:
    """
    Resuelve el "alumno propio" para un User autenticado.

    Orden (robusto y retrocompatible):
    1) Alumno.usuario == user (modelo nuevo / vínculo explícito)
    2) Alumno.id_alumno == user.username (si el username se usa como legajo)
    3) Alumno.padre == user, SOLO si hay 1 hijo (caso legacy: usuario compartido / familia)
    """
    # 1) vínculo explícito (si existe el campo)
    try:
        a = Alumno.objects.filter(usuario=user).first()
        if a:
            return AlumnoResolution(a, "usuario_link", 1)
    except Exception:
        # si el modelo no tiene campo `usuario`, ignoramos
        pass

    # 2) username == legajo
    try:
        uname = (getattr(user, "username", "") or "").strip()
        if uname:
            # case-insensitive para evitar problemas de mayúsculas/minúscula
            a = Alumno.objects.filter(id_alumno__iexact=uname).first()
            if a:
                return AlumnoResolution(a, "username_as_legajo", 1)
    except Exception:
        pass

    # 3) usuario compartido (padre) con único hijo
    try:
        qs = Alumno.objects.filter(padre=user)
        n = qs.count()
        if n == 1:
            return AlumnoResolution(qs.first(), "padre_unico_hijo", 1)
        if n > 1:
            return AlumnoResolution(None, "padre_multiples_hijos", n)
    except Exception:
        pass

    return AlumnoResolution(None, "no_match", 0)


def resolve_hijos_for_padre(user: User) -> List[Alumno]:
    try:
        return list(Alumno.objects.filter(padre=user).order_by("curso", "nombre"))
    except Exception:
        return []


def build_context_for_user(user: User, groups: List[str]) -> Dict[str, Any]:
    """
    Construye un contexto estable para el front:
    - alumno_propio: para rol Alumnos (o cuando se puede inferir unívocamente)
    - hijos: para rol Padres
    - meta de resolución para debug/soporte
    """
    ctx: Dict[str, Any] = {}

    # Alumno (si aplica)
    if "Alumnos" in groups:
        r = resolve_alumno_for_user(user)
        ctx["alumno"] = alumno_to_dict(r.alumno)
        ctx["alumno_resolution"] = {"method": r.method, "candidates": r.candidates}
        if ctx["alumno"] is None and r.method == "padre_multiples_hijos":
            # Ayuda al front (si algún día querés selector)
            hijos = resolve_hijos_for_padre(user)
            ctx["hijos"] = [alumno_to_dict(a) for a in hijos]
    # Padre (si aplica)
    if "Padres" in groups:
        hijos = resolve_hijos_for_padre(user)
        ctx["hijos"] = [alumno_to_dict(a) for a in hijos]

    return ctx
