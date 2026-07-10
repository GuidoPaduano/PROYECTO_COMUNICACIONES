# calificaciones/api_asistencias/_helpers.py
"""
Data/query helpers, parsers, normalizers, serializers y bulk upsert
para la API de asistencias.
"""
from __future__ import annotations

import json
from datetime import date as date_cls
from typing import Any, Dict, List, Optional

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.http import QueryDict

from rest_framework.response import Response

from ..course_access import (
    build_course_ref,
    build_course_membership_q,
    course_ref_matches,
    get_assignment_course_refs,
)
from ..contexto import resolve_alumno_for_user
from ..models import Alumno, Asistencia, Notificacion
from ..models import resolve_school_course_for_value
from ..schools import scope_queryset_to_school
from ..user_groups import get_user_group_names
from ..utils_cursos import get_course_label, get_school_course_choices
from ..utils_pagination import paginate_queryset

from ._acceso import _is_directivo_user, _is_preceptor_user, _is_profesor_user

try:
    from ..models_preceptores import PreceptorCurso, ProfesorCurso  # type: ignore
except Exception:
    PreceptorCurso = None
    ProfesorCurso = None


# =========================================================
# Helpers de modelo / queryset
# =========================================================

def _has_model_field(model, name: str) -> bool:
    try:
        model._meta.get_field(name)
        return True
    except Exception:
        return False


def _alumno_base_qs(school=None):
    return scope_queryset_to_school(
        Alumno.objects.select_related("school", "school_course", "padre", "usuario"),
        school,
    )


def _asistencia_base_qs(school=None):
    return scope_queryset_to_school(
        Asistencia.objects.select_related("alumno", "alumno__school_course"),
        school,
    )


def _alumnos_por_curso_qs(curso: str, *, school=None, school_course=None):
    curso = str(curso or "").strip()
    if not curso:
        return Alumno.objects.none()

    resolved_school_course = school_course
    if resolved_school_course is None and school is not None:
        resolved_school_course = resolve_school_course_for_value(school=school, curso=curso)
    course_q = build_course_membership_q(
        school_course_id=getattr(resolved_school_course, "id", None),
        course_code=curso,
        school_course_field="school_course",
        code_field="curso",
    )
    if course_q is None:
        return Alumno.objects.none()
    return _alumno_base_qs(school).filter(course_q)


# =========================================================
# Parsers / normalizers
# =========================================================

def _first_scalar(v: Any) -> Any:
    """Si viene ['x'] (QueryDict/dict(request.data)), devolvé 'x'."""
    if isinstance(v, (list, tuple)):
        return v[0] if v else None
    return v


def _try_parse_json(value: Any) -> Any:
    """Si value es string JSON, intenta parsearlo."""
    if not isinstance(value, str):
        return value
    s = value.strip()
    if not s:
        return value
    if not (s.startswith("{") or s.startswith("[") or s.startswith('"')):
        return value
    try:
        return json.loads(s)
    except Exception:
        return value


def _coerce_json(request) -> Dict[str, Any]:
    """Lee JSON incluso cuando request.data viene vacío o es form-data.

    ✅ FIX importante:
    - request.data puede ser QueryDict o dict "raro" y a veces termina como listas.
    - Normalizamos a {k: value_scalar} para que 'curso' no sea ['1A'].
    """
    try:
        if getattr(request, "data", None) is not None:
            data = request.data

            # Si es QueryDict real (form-data), normalizamos escalares.
            if isinstance(data, QueryDict):
                out: Dict[str, Any] = {}
                for k in list(data.keys()):
                    out[k] = _first_scalar(data.get(k))
                return out

            # Si ya es dict normal
            if isinstance(data, dict):
                return dict(data)
    except Exception:
        pass

    try:
        raw = (request.body or b"").decode("utf-8")
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _norm_bool(v: Any) -> Optional[bool]:
    """Normaliza booleanos que pueden venir como string ("true"/"false")."""
    if isinstance(v, bool):
        return v
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("true", "1", "si", "sí", "yes", "y", "on"):
        return True
    if s in ("false", "0", "no", "off"):
        return False
    return None


# =========================================================
# Notificaciones
# =========================================================

def _resolver_destinatarios_notif(alumno: Alumno, legajo_user_map=None):
    """Destinatarios de notificación:
    - Padre asignado (alumno.padre) si existe
    - Alumno.usuario si existe
    - Fallback: User.username == alumno.id_alumno (legajo)
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

    _add(getattr(alumno, "padre", None))
    alumno_usuario = getattr(alumno, "usuario", None)
    _add(alumno_usuario)

    try:
        legajo = (getattr(alumno, "id_alumno", "") or "").strip()
        alumno_username = str(getattr(alumno_usuario, "username", "") or "").strip().lower()
        if legajo and alumno_username != legajo.lower():
            if legajo_user_map is not None:
                _add(legajo_user_map.get(legajo))
            else:
                User = get_user_model()
                _add(User.objects.filter(username__iexact=legajo).first())
    except Exception:
        pass

    return destinatarios


def _notify_inasistencias_bulk(*, alumno_ids: List[int], fecha, tipo_asistencia: str, actor=None, school=None):
    if not alumno_ids:
        return 0
    try:
        qs = _alumno_base_qs(school).filter(id__in=alumno_ids)
    except Exception:
        qs = scope_queryset_to_school(Alumno.objects.filter(id__in=alumno_ids), school)

    created = 0
    notifs = []
    fecha_str = str(fecha) if fecha else ""
    tipo_label = _tipo_label(tipo_asistencia) if tipo_asistencia else ""
    actor_label = ""
    try:
        actor_label = (actor.get_full_name() or actor.username).strip() if actor else ""
    except Exception:
        actor_label = ""

    legajo_user_map = {}
    try:
        User = get_user_model()
        legajos = [
            (getattr(a, "id_alumno", "") or "").strip()
            for a in qs
            if (getattr(a, "id_alumno", "") or "").strip()
        ]
        if legajos:
            users = User.objects.filter(username__in=legajos)
            legajo_user_map = {u.username: u for u in users}
    except Exception:
        legajo_user_map = {}

    for a in qs:
        destinatarios = _resolver_destinatarios_notif(a, legajo_user_map=legajo_user_map)
        if not destinatarios:
            continue

        alumno_nombre = (getattr(a, "apellido", "") + " " + getattr(a, "nombre", "")).strip()
        if not alumno_nombre:
            alumno_nombre = getattr(a, "nombre", "") or str(getattr(a, "id_alumno", "")) or "Alumno"

        course_name = _school_course_name_for(alumno=a)
        titulo = f"Inasistencia registrada: {alumno_nombre}"
        desc_parts = [f"Alumno: {alumno_nombre}"]
        if course_name:
            desc_parts.append(f"Curso: {course_name}")
        if tipo_label:
            desc_parts.append(f"Tipo: {tipo_label}")
        if fecha_str:
            desc_parts.append(f"Fecha: {fecha_str}")
        if actor_label:
            desc_parts.append(f"Registrado por: {actor_label}")
        descripcion = " · ".join([p for p in desc_parts if p]).strip()

        for dest in destinatarios:
            notifs.append(
                Notificacion(
                    school=getattr(a, "school", None) or school,
                    destinatario=dest,
                    tipo="inasistencia",
                    titulo=titulo,
                    descripcion=descripcion,
                    url=f"/alumnos/{getattr(a, 'id', '')}/?tab=asistencias",
                    leida=False,
                    meta={
                        "alumno_id": getattr(a, "id", None),
                        "alumno_legajo": getattr(a, "id_alumno", None),
                        "school_course_id": getattr(a, "school_course_id", None),
                        "school_course_name": course_name,
                        "fecha": fecha_str,
                        "tipo_asistencia": tipo_asistencia,
                    },
                )
            )

    if notifs:
        try:
            Notificacion.objects.bulk_create(notifs)
            created = len(notifs)
        except Exception:
            for n in notifs:
                try:
                    n.save()
                    created += 1
                except Exception:
                    pass

    for n in notifs:
        try:
            to_email = (getattr(n.destinatario, "email", "") or "").strip()
            if to_email:
                from ..resend_email import send_resend_email
                send_resend_email(
                    to_email=to_email,
                    subject=n.titulo,
                    text=n.descripcion,
                )
        except Exception:
            pass

    return created


# =========================================================
# Normalizadores de estado
# =========================================================

def _norm_estado(v: Any) -> Optional[Dict[str, bool]]:
    """Normaliza un estado de asistencia a {presente: bool, tarde: bool}.

    Acepta:
    - bool: True => presente, False => ausente
    - str: "presente" | "ausente" | "tarde" (y variantes)
    - dict: {estado:"tarde"} o {presente:true, tarde:true}
    """
    # dict explícito
    if isinstance(v, dict):
        estado = (v.get("estado") or v.get("status") or v.get("tipo") or "").strip().lower()
        if estado in ("tarde", "late", "llegotarde", "llego_tarde", "llegó_tarde", "llego tarde", "llegó tarde"):
            return {"presente": True, "tarde": True}
        if estado in ("presente", "asistio", "asistió"):
            return {"presente": True, "tarde": bool(_norm_bool(v.get("tarde")) or False)}
        if estado in ("ausente", "falto", "faltó", "no", "absent"):
            return {"presente": False, "tarde": False}

        b_pres = _norm_bool(v.get("presente"))
        b_tar = _norm_bool(v.get("tarde"))
        if b_pres is None and "inasistente" in v:
            bi = _norm_bool(v.get("inasistente"))
            if bi is not None:
                b_pres = (not bi)
        if b_pres is None and b_tar is None:
            return None
        presente = bool(b_pres) if b_pres is not None else True
        tarde = bool(b_tar) if b_tar is not None else False
        if not presente:
            tarde = False
        return {"presente": presente, "tarde": tarde}

    # bool / bool-like
    b = _norm_bool(v)
    if b is not None:
        return {"presente": bool(b), "tarde": False}

    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("tarde", "late", "l", "lt", "llegotarde", "llego_tarde", "llegó_tarde", "llego tarde", "llegó tarde"):
            return {"presente": True, "tarde": True}
        if s in ("presente", "p", "ok", "asistio", "asistió", "1", "true", "si", "sí", "yes", "y", "on"):
            return {"presente": True, "tarde": False}
        if s in ("ausente", "a", "no", "0", "false", "off", "falto", "faltó", "absent"):
            return {"presente": False, "tarde": False}

    # fallback
    if v is None:
        return None
    return {"presente": bool(v), "tarde": False}


def _infer_estado(item: Dict[str, Any]) -> Optional[Dict[str, bool]]:
    """Infere estado desde un item dict (para formatos B)."""
    st = _norm_estado(item)
    if st is not None:
        return st

    pres = _infer_presente(item)
    if pres is None:
        return None

    # tardanza por campo
    b_tar = _norm_bool(item.get("tarde"))
    tarde = bool(b_tar) if b_tar is not None else False

    estado = (item.get("estado") or "").strip().lower()
    if estado in ("tarde", "late", "llegotarde", "llego_tarde", "llegó_tarde", "llego tarde", "llegó tarde"):
        tarde = True
        pres = True

    if not pres:
        tarde = False

    return {"presente": bool(pres), "tarde": bool(tarde)}


def _infer_presente(item: Dict[str, Any]) -> Optional[bool]:
    # Preferimos 'presente'
    if "presente" in item:
        b = _norm_bool(item.get("presente"))
        if b is not None:
            return b

    # A veces viene 'inasistente'
    if "inasistente" in item:
        b = _norm_bool(item.get("inasistente"))
        if b is not None:
            return (not b)

    # O 'estado'/'tipo' con string
    estado = (item.get("estado") or item.get("tipo") or item.get("tipo_asistencia") or "").strip().lower()
    if estado in ("presente", "asistio", "asistió"):
        return True
    if estado in ("inasistente", "ausente", "falta", "tarde", "justificada"):
        return False
    return None


def _extract_items(payload: Any) -> List[Dict[str, Any]]:
    """Acepta múltiples formatos y devuelve una lista de items."""
    if payload is None:
        return []

    payload = _try_parse_json(payload)

    if isinstance(payload, list):
        out = []
        for x in payload:
            x = _try_parse_json(x)
            if isinstance(x, dict):
                out.append(x)
        return out

    if not isinstance(payload, dict):
        return []

    for nested_key in ("payload", "body", "json"):
        if nested_key in payload:
            nested = _try_parse_json(payload.get(nested_key))
            items = _extract_items(nested)
            if items:
                return items

    for k in ("items", "asistencias", "data", "rows", "registros", "seleccion", "selection"):
        if k in payload:
            v = _try_parse_json(payload.get(k))
            if isinstance(v, list):
                out = []
                for x in v:
                    x = _try_parse_json(x)
                    if isinstance(x, dict):
                        out.append(x)
                return out
            if isinstance(v, dict):
                return [v]

    for k in ("item", "asistencia", "registro"):
        if k in payload:
            v = _try_parse_json(payload.get(k))
            if isinstance(v, dict):
                return [v]
            if isinstance(v, list):
                out = []
                for x in v:
                    x = _try_parse_json(x)
                    if isinstance(x, dict):
                        out.append(x)
                return out

    if any(key in payload for key in ("alumno_id", "alumno", "id_alumno", "legajo")):
        return [payload]

    return []


# =========================================================
# Helpers de curso / tipo / serialización
# =========================================================

def _cursos_choices(school=None) -> List[tuple]:
    return list(get_school_course_choices(school=school))


def _tipo_choices() -> List[tuple]:
    return list(getattr(Asistencia, "TIPO_ASISTENCIA", []))


def _curso_label(curso: str, school=None) -> str:
    return get_course_label(curso, school=school)


def _tipo_label(tipo_asistencia: str) -> str:
    return dict(_tipo_choices()).get(tipo_asistencia, tipo_asistencia)


def _school_course_name_for(*, alumno: Optional[Alumno] = None, school_course=None, curso: str = "", school=None) -> Optional[str]:
    resolved_school_course = school_course or getattr(alumno, "school_course", None)
    name = getattr(resolved_school_course, "name", None) or getattr(resolved_school_course, "code", None)
    if name:
        return str(name)
    course_code = str(getattr(alumno, "curso", None) or curso or "").strip()
    if course_code:
        return _curso_label(course_code, school=school) or course_code
    return None


def _course_payload(*, alumno: Optional[Alumno] = None, school_course=None, curso: str = "", school=None) -> Dict[str, Any]:
    course_code = str(
        getattr(school_course, "code", None)
        or getattr(alumno, "curso", None)
        or curso
        or ""
    ).strip()
    course_id = getattr(school_course, "id", None)
    if course_id is None:
        course_id = getattr(alumno, "school_course_id", None)
    return {
        "curso": course_code or None,
        "school_course_id": course_id,
        "school_course_name": _school_course_name_for(
            alumno=alumno,
            school_course=school_course,
            curso=course_code,
            school=school,
        ),
    }


def _public_course_payload(*, alumno: Optional[Alumno] = None, school_course=None, curso: str = "", school=None) -> Dict[str, Any]:
    return {
        key: value
        for key, value in _course_payload(
            alumno=alumno,
            school_course=school_course,
            curso=curso,
            school=school,
        ).items()
        if key != "curso"
    }


def _serialize_alumno_brief(alumno: Alumno, *, school=None) -> Dict[str, Any]:
    item = {
        "id": alumno.id,
        "id_alumno": alumno.id_alumno,
        "nombre": alumno.nombre,
    }
    item.update(_public_course_payload(alumno=alumno, school=school))
    return item


def _serialize_asistencia_item(obj: Asistencia, *, alumno: Optional[Alumno] = None, curso: str = "", school=None) -> Dict[str, Any]:
    alumno_obj = alumno or getattr(obj, "alumno", None)
    item = {
        "id": obj.id,
        "alumno_id": getattr(alumno_obj, "id", None),
        "id_alumno": getattr(alumno_obj, "id_alumno", None),
        "fecha": str(obj.fecha),
        "tipo_asistencia": obj.tipo_asistencia,
        "tipo_label": _tipo_label(obj.tipo_asistencia),
        "presente": bool(obj.presente),
        "tarde": bool(getattr(obj, "tarde", False)),
        "justificada": bool(getattr(obj, "justificada", False)),
        "firmada": bool(getattr(obj, "firmada", False)),
        "firmada_en": obj.firmada_en.isoformat() if getattr(obj, "firmada_en", None) else None,
        "falta_valor": 0.0
        if bool(getattr(obj, "justificada", False))
        else (1.0 if (not bool(obj.presente)) else (0.5 if bool(getattr(obj, "tarde", False)) else 0.0)),
        "observacion": getattr(obj, "observacion", "") or "",
    }
    item.update(
        {
            k: v
            for k, v in _public_course_payload(alumno=alumno_obj, curso=curso, school=school).items()
        }
    )
    return item


# =========================================================
# Helpers de permisos por curso (dependen de _acceso)
# =========================================================

def _cursos_de_usuario(user, school=None) -> List[str]:
    """Cursos permitidos para el usuario."""
    todos = [c[0] for c in _cursos_choices(school=school)]

    if getattr(user, "is_superuser", False):
        return todos

    if _is_directivo_user(user):
        return todos

    refs = _course_refs_de_usuario(user, school=school)
    if refs:
        asignados: List[str] = []
        seen = set()
        for curso in todos:
            normalized = str(curso or "").strip().upper()
            if not normalized or normalized in seen:
                continue
            if course_ref_matches(refs, school=school, course_code=normalized):
                seen.add(normalized)
                asignados.append(curso)
        return asignados

    asignados: List[str] = []
    if not asignados:
        try:
            grupos = set(get_user_group_names(user))
            asignados = [c for c in todos if c in grupos]
        except Exception:
            asignados = []

    validos = set(todos)
    return sorted([c for c in asignados if c in validos])


def _course_refs_de_usuario(user, school=None):
    if getattr(user, "is_superuser", False) or _is_directivo_user(user):
        return []

    school_id = getattr(school, "id", None) or 0
    cached_refs_by_school = getattr(user, "_cached_course_refs_by_school", None)
    if isinstance(cached_refs_by_school, dict) and school_id in cached_refs_by_school:
        return list(cached_refs_by_school[school_id])

    refs = []
    groups = set(get_user_group_names(user))
    has_explicit_groups = bool(groups)
    include_preceptor = (not has_explicit_groups) or ("Preceptores" in groups) or ("Preceptor" in groups)
    include_profesor = (not has_explicit_groups) or ("Profesores" in groups) or ("Profesor" in groups)

    if include_preceptor and PreceptorCurso is not None:
        try:
            refs.extend(
                get_assignment_course_refs(
                    scope_queryset_to_school(PreceptorCurso.objects.filter(preceptor=user), school)
                )
            )
        except Exception:
            pass

    if include_profesor and ProfesorCurso is not None:
        try:
            refs.extend(
                get_assignment_course_refs(
                    scope_queryset_to_school(ProfesorCurso.objects.filter(profesor=user), school)
                )
            )
        except Exception:
            pass

    try:
        if not isinstance(cached_refs_by_school, dict):
            cached_refs_by_school = {}
        cached_refs_by_school[school_id] = tuple(refs)
        setattr(user, "_cached_course_refs_by_school", cached_refs_by_school)
    except Exception:
        pass

    return refs


def _can_manage_course_attendance(user, curso: str = "", *, school=None, school_course=None) -> bool:
    curso = str(curso or "").strip()
    if not curso and school_course is None:
        return False

    if getattr(user, "is_superuser", False):
        return True
    if _is_directivo_user(user):
        return True
    if not (_is_preceptor_user(user) or _is_profesor_user(user)):
        return False

    refs = _course_refs_de_usuario(user, school=school)
    if refs:
        return course_ref_matches(
            refs,
            school=school,
            school_course_id=getattr(school_course, "id", None),
            course_code=curso,
        )

    permitidos = _cursos_de_usuario(user, school=school)
    course_code_refs = [
        build_course_ref(school=school, course_code=permitido)
        for permitido in permitidos
        if str(permitido or "").strip()
    ]
    return course_ref_matches(
        course_code_refs,
        school=school,
        school_course_id=getattr(school_course, "id", None),
        course_code=curso,
    )


def _can_view_alumno_asistencia(user, alumno: Alumno) -> bool:
    if user is None or alumno is None:
        return False

    if getattr(user, "is_superuser", False) or _is_directivo_user(user):
        return True

    if getattr(alumno, "padre_id", None) == getattr(user, "id", None):
        return True
    if getattr(alumno, "usuario_id", None) == getattr(user, "id", None):
        return True

    try:
        resolution = resolve_alumno_for_user(user, school=getattr(alumno, "school", None))
        if resolution.alumno is not None and getattr(resolution.alumno, "id", None) == getattr(alumno, "id", None):
            return True
    except Exception:
        pass

    return _can_manage_course_attendance(
        user,
        getattr(alumno, "curso", None),
        school=getattr(alumno, "school", None),
        school_course=getattr(alumno, "school_course", None),
    )


# =========================================================
# Response helpers
# =========================================================

def _ok_response(payload: Dict[str, Any], status: int = 200) -> Response:
    return Response(payload, status=status)


def _err(detail: str, status: int = 400, extra: Optional[Dict[str, Any]] = None) -> Response:
    payload = {"detail": detail}
    if extra:
        payload.update(extra)
    return Response(payload, status=status)


# =========================================================
# Bulk upsert
# =========================================================

def _bulk_upsert_asistencias(
    alumno_ids: List[int],
    fecha,
    tipo_asistencia: str,
    estado_by_alumno_id: Dict[int, Dict[str, bool]],
    school=None,
) -> Dict[str, Any]:
    """
    Upsert masivo (bulk) para evitar timeouts.
    - Trae existentes en 1 query
    - bulk_update para los que ya están
    - bulk_create para los nuevos

    estado_by_alumno_id: { alumno_id: {presente: bool, tarde: bool} }
    """
    if not alumno_ids:
        return {"guardadas": 0, "errores": 0}

    existentes = list(
        scope_queryset_to_school(
            Asistencia.objects.filter(
                alumno_id__in=alumno_ids,
                fecha=fecha,
                tipo_asistencia=tipo_asistencia,
            ),
            school,
        )
    )
    by_aid = {a.alumno_id: a for a in existentes}
    alumnos = {
        alumno.id: alumno
        for alumno in _alumno_base_qs(school).filter(id__in=alumno_ids)
    }

    to_update: List[Asistencia] = []
    to_create: List[Asistencia] = []
    ausentes: List[int] = []
    afectados: List[int] = []

    for aid in alumno_ids:
        st = estado_by_alumno_id.get(aid) or {"presente": True, "tarde": False}
        presente = bool(st.get("presente", True))
        tarde = bool(st.get("tarde", False))
        if not presente:
            tarde = False

        alumno = alumnos.get(aid)
        resolved_school = getattr(alumno, "school", None) or school
        obj = by_aid.get(aid)
        if obj is not None:
            changed = False
            prev_presente = bool(obj.presente)
            if bool(obj.presente) != presente:
                obj.presente = presente
                changed = True
            if bool(getattr(obj, "tarde", False)) != tarde:
                setattr(obj, "tarde", tarde)
                changed = True
            # Si pasa a Presente (no tarde), automáticamente deja de estar justificada
            if presente and (not tarde) and bool(getattr(obj, "justificada", False)):
                setattr(obj, "justificada", False)
                changed = True
            resolved_school_id = getattr(resolved_school, "id", None)
            if resolved_school_id is not None and getattr(obj, "school_id", None) != resolved_school_id:
                obj.school = resolved_school
                changed = True
            if changed:
                to_update.append(obj)
                afectados.append(aid)
                if prev_presente and (not presente):
                    ausentes.append(aid)
        else:
            to_create.append(
                Asistencia(
                    school=resolved_school,
                    alumno_id=aid,
                    fecha=fecha,
                    tipo_asistencia=tipo_asistencia,
                    presente=presente,
                    tarde=tarde,
                )
            )
            afectados.append(aid)
            if not presente:
                ausentes.append(aid)

    with transaction.atomic():
        if to_update:
            Asistencia.objects.bulk_update(to_update, ["presente", "tarde", "justificada", "school"])
        if to_create:
            try:
                Asistencia.objects.bulk_create(to_create, batch_size=500)
            except Exception:
                for obj in to_create:
                    alumno = alumnos.get(obj.alumno_id)
                    resolved_school = getattr(alumno, "school", None) or school
                    Asistencia.objects.update_or_create(
                        alumno_id=obj.alumno_id,
                        fecha=obj.fecha,
                        tipo_asistencia=obj.tipo_asistencia,
                        defaults={
                            "school": resolved_school,
                            "presente": bool(obj.presente),
                            "tarde": bool(getattr(obj, "tarde", False)),
                            "justificada": False,
                        },
                    )

    return {"guardadas": len(alumno_ids), "errores": 0, "ausentes": ausentes, "afectados": sorted(set(afectados))}


# =========================================================
# Respuesta de asistencias por alumno (helper compartido)
# =========================================================

def _asistencias_alumno_response(alumno, *, school=None, request=None):
    qs = _asistencia_base_qs(school).filter(alumno=alumno).order_by("-fecha", "-id")
    if request is not None:
        items, pagination = paginate_queryset(qs, request)
    else:
        items = qs
        pagination = {"page": 1, "page_size": len(qs), "total": len(qs), "total_pages": 1, "has_next": False, "has_previous": False}
    results = [
        _serialize_asistencia_item(asistencia, alumno=alumno, school=school)
        for asistencia in items
    ]
    return Response(
        {
            "alumno": _serialize_alumno_brief(alumno, school=school),
            "results": results,
            **pagination,
        }
    )
