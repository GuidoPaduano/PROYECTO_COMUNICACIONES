# calificaciones/api_asistencias.py
from __future__ import annotations

from datetime import date as date_cls
import json
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.utils.dateparse import parse_date
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.http import QueryDict

from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    parser_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
from .jwt_auth import CookieJWTAuthentication as JWTAuthentication

from .course_access import (
    build_course_ref,
    build_course_membership_q,
    course_ref_matches,
    get_assignment_course_refs,
)
from .contexto import resolve_alumno_for_user
from .models import Alumno, Asistencia, Notificacion
from .models import resolve_school_course_for_value
from .utils_cursos import get_course_label, get_school_course_choices, resolve_course_reference
from .alerts_inasistencias import evaluar_alertas_inasistencia_por_alumnos, evaluar_alerta_inasistencia
from .schools import get_request_school, scope_queryset_to_school
from .user_groups import get_user_group_names, user_in_groups

try:
    # Si existen los modelos reales de preceptor/profesor → cursos
    from .models_preceptores import PreceptorCurso, ProfesorCurso  # type: ignore
except Exception:
    PreceptorCurso = None
    ProfesorCurso = None


LEGACY_COURSE_DEPRECATED_DETAIL = "El parámetro 'curso' está deprecado en este endpoint. Usa school_course_id."


# =========================================================
# Roles / permisos
# =========================================================
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


# =========================================================
# Helpers
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

    return created



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


def _cursos_choices(school=None) -> List[tuple[str, str]]:
    return list(get_school_course_choices(school=school))


def _tipo_choices() -> List[tuple[str, str]]:
    return list(getattr(Asistencia, "TIPO_ASISTENCIA", []))


def _curso_label(curso: str, school=None) -> str:
    return get_course_label(curso, school=school)


def _tipo_label(tipo_asistencia: str) -> str:
    return dict(_tipo_choices()).get(tipo_asistencia, tipo_asistencia)


def _school_course_name_for(*, alumno: Alumno | None = None, school_course=None, curso: str = "", school=None) -> Optional[str]:
    resolved_school_course = school_course or getattr(alumno, "school_course", None)
    name = getattr(resolved_school_course, "name", None) or getattr(resolved_school_course, "code", None)
    if name:
        return str(name)
    course_code = str(getattr(alumno, "curso", None) or curso or "").strip()
    if course_code:
        return _curso_label(course_code, school=school) or course_code
    return None


def _course_payload(*, alumno: Alumno | None = None, school_course=None, curso: str = "", school=None) -> Dict[str, Any]:
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


def _public_course_payload(*, alumno: Alumno | None = None, school_course=None, curso: str = "", school=None) -> Dict[str, Any]:
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


def _serialize_asistencia_item(obj: Asistencia, *, alumno: Alumno | None = None, curso: str = "", school=None) -> Dict[str, Any]:
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


def _ok_response(payload: Dict[str, Any], status: int = 200) -> Response:
    return Response(payload, status=status)


def _err(detail: str, status: int = 400, extra: Optional[Dict[str, Any]] = None) -> Response:
    payload = {"detail": detail}
    if extra:
        payload.update(extra)
    return Response(payload, status=status)


def _bulk_upsert_asistencias(
    alumno_ids: List[int],
    fecha,
    tipo_asistencia: str,
    estado_by_alumno_id: Dict[int, Dict[str, bool]],
    school=None,
) -> Dict[str, Any]:
    """
    ✅ Upsert masivo (bulk) para evitar timeouts.
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
            # ✅ Si pasa a Presente (no tarde), automáticamente deja de estar justificada
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
#  Preceptor: cursos
# =========================================================
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def preceptor_cursos(request):
    active_school = get_request_school(request)
    cursos = _cursos_de_usuario(request.user, school=active_school)
    data = []
    for c in cursos:
        school_course = resolve_school_course_for_value(school=active_school, curso=c) if active_school is not None else None
        data.append(
            {
                "curso": c,
                "code": c,
                "nombre": _curso_label(c, school=active_school),
                "school_course_id": getattr(school_course, "id", None),
            }
        )
    return _ok_response({"cursos": data})


# =========================================================
#  Tipos de asistencia (combo del front)
# =========================================================
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def tipos_asistencia(request):
    data = []
    for v, lbl in _tipo_choices():
        data.append({"id": v, "nombre": lbl, "value": v, "label": lbl})
    return Response(data)


# =========================================================
#  Registrar asistencias
# =========================================================
@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def registrar_asistencias(request):
    active_school = get_request_school(request)
    payload = _coerce_json(request)

    # ✅ NUEVO: por defecto NO devolvemos items (para que sea rápido y no pese)
    return_items = _norm_bool(payload.get("return_items"))
    if return_items is None:
        return_items = False

    # -----------------------------------------------------
    # Formato C: mapping id->estado
    #   {school_course_id, fecha, tipo_asistencia|tipo, asistencias:{ "418": true, ... }}
    # -----------------------------------------------------
    if isinstance(payload, dict) and ("asistencias" in payload or "asistenciasPayload" in payload):
        raw_map = payload.get("asistencias", payload.get("asistenciasPayload"))
        raw_map = _try_parse_json(raw_map)

        if isinstance(raw_map, dict):
            school_course_ref, curso, course_error = resolve_course_reference(
                school=active_school,
                raw_course=_first_scalar(payload.get("curso") or ""),
                raw_school_course_id=_first_scalar(payload.get("school_course_id") or ""),
                required=True,
            )
            tipo_asistencia = str(
                _first_scalar(payload.get("tipo_asistencia") or payload.get("tipo") or payload.get("materia") or "") or ""
            ).strip()

            fecha_raw = _first_scalar(payload.get("fecha") or payload.get("date"))
            fecha = parse_date(str(fecha_raw)) if fecha_raw else date_cls.today()

            if course_error:
                return _err(course_error, 400)
            if not tipo_asistencia:
                return _err("Falta tipo_asistencia/tipo", 400)
            if active_school is not None and school_course_ref is None:
                return _err("No existe ese curso en el colegio activo.", 400)

            if not _can_manage_course_attendance(request.user, curso, school=active_school, school_course=school_course_ref):
                return _err("No tenés permisos para ese curso.", 403)

            # ✅ NUEVO: resolvemos alumnos en BULK (evita N queries)
            keys = [str(k).strip() for k in raw_map.keys()]
            id_ints: List[int] = []
            legajos: List[str] = []
            for k in keys:
                if k.isdigit():
                    try:
                        id_ints.append(int(k))
                    except Exception:
                        pass
                else:
                    legajos.append(k)

            alumnos_qs = _alumnos_por_curso_qs(curso, school=active_school).filter(
                Q(pk__in=id_ints) | Q(id_alumno__in=legajos)
            )

            alumnos_list = list(alumnos_qs)
            by_pk = {str(a.id): a for a in alumnos_list}
            by_legajo = {str(getattr(a, "id_alumno", "")).strip(): a for a in alumnos_list}

            estado_by_id: Dict[int, Dict[str, bool]] = {}
            errores = 0

            for k, v in raw_map.items():
                key = str(k).strip()
                st = _norm_estado(v)
                if st is None:
                    b = _norm_bool(v)
                    if b is None:
                        b = bool(v)
                    st = {"presente": bool(b), "tarde": False}

                alumno = by_pk.get(key) if key.isdigit() else by_legajo.get(key)
                if not alumno:
                    errores += 1
                    continue

                if not bool(st.get("presente", True)):
                    st["tarde"] = False

                estado_by_id[int(alumno.id)] = {"presente": bool(st.get("presente", True)), "tarde": bool(st.get("tarde", False))}

            alumno_ids = sorted(list(estado_by_id.keys()))
            if not alumno_ids and errores > 0:
                return _err(
                    "No se pudo guardar ninguna asistencia. Revisá que las claves de 'asistencias' sean IDs (PK) o legajos válidos del curso.",
                    400,
                    {"guardadas": 0, "errores": errores},
                )

            # ✅ NUEVO: upsert masivo
            try:
                res = _bulk_upsert_asistencias(
                    alumno_ids,
                    fecha,
                    tipo_asistencia,
                    estado_by_id,
                    school=active_school,
                )
            except Exception:
                return _err("Error guardando asistencias (bulk).", 500)

            try:
                _notify_inasistencias_bulk(
                    alumno_ids=sorted(set(res.get("ausentes") or [])),
                    fecha=fecha,
                    tipo_asistencia=tipo_asistencia,
                    actor=getattr(request, "user", None),
                    school=active_school,
                )
            except Exception:
                pass
            if getattr(settings, "ALERTAS_INASISTENCIAS_SYNC_EN_GUARDADO", False):
                try:
                    evaluar_alertas_inasistencia_por_alumnos(
                        alumno_ids=sorted(set(res.get("afectados") or [])),
                        tipo_asistencia=tipo_asistencia,
                        actor=getattr(request, "user", None),
                    )
                except Exception:
                    pass

            items_out: List[Dict[str, Any]] = []
            if return_items and alumno_ids:
                qs = scope_queryset_to_school(
                    Asistencia.objects.filter(
                        alumno_id__in=alumno_ids,
                        fecha=fecha,
                        tipo_asistencia=tipo_asistencia,
                    ),
                    active_school,
                ).select_related("alumno", "alumno__school_course")
                for obj in qs:
                    items_out.append(_serialize_asistencia_item(obj, curso=curso, school=active_school))
                        # ✅ NUEVO: equivalente de falta (Ausente=1, Tarde=0.5, Presente=0)

            response_payload = {
                "fecha": str(fecha),
                "tipo_asistencia": tipo_asistencia,
                "guardadas": res.get("guardadas", 0),
                "errores": int(errores) + int(res.get("errores", 0)),
                "items": items_out if return_items else [],
            }
            response_payload.update(
                _public_course_payload(school_course=school_course_ref, curso=curso, school=active_school)
            )
            return _ok_response(response_payload)

    # -----------------------------------------------------
    # Formato A: presentes/tardes por curso (lista de IDs)
    #   {school_course_id, fecha, tipo_asistencia|tipo, presentes:[ids]}
    # -----------------------------------------------------
    if isinstance(payload, dict) and (
        "presentes" in payload or "presentes_ids" in payload or "presentesId" in payload
    ):
        school_course_ref, curso, course_error = resolve_course_reference(
            school=active_school,
            raw_course=_first_scalar(payload.get("curso") or ""),
            raw_school_course_id=_first_scalar(payload.get("school_course_id") or ""),
            required=True,
        )
        tipo_asistencia = str(
            _first_scalar(payload.get("tipo_asistencia") or payload.get("tipo") or payload.get("materia") or "") or ""
        ).strip()

        fecha_raw = _first_scalar(payload.get("fecha") or payload.get("date"))
        fecha = parse_date(str(fecha_raw)) if fecha_raw else date_cls.today()

        presentes = payload.get("presentes") or payload.get("presentes_ids") or payload.get("presentesId") or []
        tardes = payload.get("tardes") or payload.get("tardes_ids") or payload.get("tardesId") or []
        presentes = _try_parse_json(presentes)
        if not isinstance(presentes, list):
            presentes = []
        tardes = _try_parse_json(tardes)
        if not isinstance(tardes, list):
            tardes = []

        if course_error:
            return _err(course_error, 400)
        if not tipo_asistencia:
            return _err("Falta tipo_asistencia/tipo", 400)
        if active_school is not None and school_course_ref is None:
            return _err("No existe ese curso en el colegio activo.", 400)

        if not _can_manage_course_attendance(request.user, curso, school=active_school, school_course=school_course_ref):
            return _err("No tenés permisos para ese curso.", 403)

        alumno_ids = list(_alumnos_por_curso_qs(curso, school=active_school).values_list("id", flat=True))
        if not alumno_ids:
            response_payload = {
                "fecha": str(fecha),
                "tipo_asistencia": tipo_asistencia,
                "guardadas": 0,
                "errores": 0,
                "items": [],
            }
            response_payload.update(
                _public_course_payload(school_course=school_course_ref, curso=curso, school=active_school)
            )
            return _ok_response(response_payload)

        presentes_set = set()
        for x in presentes:
            try:
                presentes_set.add(int(x))
            except Exception:
                pass
        tardes_set = set()
        for x in tardes:
            try:
                tardes_set.add(int(x))
            except Exception:
                pass

        presente_by_id = {aid: (aid in presentes_set) for aid in alumno_ids}
        # ✅ FIX: el bulk upsert espera {alumno_id: {presente, tarde}}
        estado_by_id = {
            aid: {
                "presente": bool(presente_by_id[aid]) or (aid in tardes_set),
                "tarde": (aid in tardes_set),
            }
            for aid in alumno_ids
        }

        try:
            res = _bulk_upsert_asistencias(
                alumno_ids,
                fecha,
                tipo_asistencia,
                estado_by_id,
                school=active_school,
            )
        except Exception:
            return _err("Error guardando asistencias (bulk).", 500)

        try:
            _notify_inasistencias_bulk(
                alumno_ids=sorted(set(res.get("ausentes") or [])),
                fecha=fecha,
                tipo_asistencia=tipo_asistencia,
                actor=getattr(request, "user", None),
                school=active_school,
            )
        except Exception:
            pass
        if getattr(settings, "ALERTAS_INASISTENCIAS_SYNC_EN_GUARDADO", False):
            try:
                evaluar_alertas_inasistencia_por_alumnos(
                    alumno_ids=sorted(set(res.get("afectados") or [])),
                    tipo_asistencia=tipo_asistencia,
                    actor=getattr(request, "user", None),
                )
            except Exception:
                pass

        items_out: List[Dict[str, Any]] = []
        if return_items:
            qs = scope_queryset_to_school(
                Asistencia.objects.filter(
                    alumno_id__in=alumno_ids,
                    fecha=fecha,
                    tipo_asistencia=tipo_asistencia,
                ),
                active_school,
            ).select_related("alumno", "alumno__school_course")
            for obj in qs:
                items_out.append(_serialize_asistencia_item(obj, curso=curso, school=active_school))

        response_payload = {
            "fecha": str(fecha),
            "tipo_asistencia": tipo_asistencia,
            "guardadas": res.get("guardadas", 0),
            "errores": res.get("errores", 0),
            "items": items_out if return_items else [],
        }
        response_payload.update(
            _public_course_payload(school_course=school_course_ref, curso=curso, school=active_school)
        )
        return _ok_response(response_payload)

    # -----------------------------------------------------
    # Formato B: items
    # -----------------------------------------------------
    items = _extract_items(payload)
    if not items:
        return _err("Falta 'asistencias', 'presentes' o 'items'.", 400)

    fecha_global = None
    tipo_global = None
    curso_global = None
    if isinstance(payload, dict):
        fg = _first_scalar(payload.get("fecha") or payload.get("date"))
        fecha_global = parse_date(str(fg)) if fg else None
        tipo_global = str(_first_scalar(payload.get("tipo_asistencia") or payload.get("tipo") or payload.get("materia") or "") or "").strip() or None
        global_school_course_ref, curso_global, global_course_error = resolve_course_reference(
            school=active_school,
            raw_course=_first_scalar(payload.get("curso") or ""),
            raw_school_course_id=_first_scalar(payload.get("school_course_id") or ""),
            required=False,
        )
        if global_course_error:
            return _err(global_course_error, 400)
        if active_school is not None and curso_global and global_school_course_ref is None:
            return _err("No existe ese curso en el colegio activo.", 400)

    guardadas = 0
    errores = 0
    items_out: List[Dict[str, Any]] = []
    afectados_ids_por_tipo: Dict[str, set[int]] = {}

    for it in items:
        it = _try_parse_json(it)
        if not isinstance(it, dict):
            errores += 1
            continue

        alumno = None
        alumno_id = it.get("alumno_id") or it.get("alumno")
        legajo = it.get("id_alumno") or it.get("legajo")

        try:
            if alumno_id:
                alumno = scope_queryset_to_school(Alumno.objects.all(), active_school).get(pk=int(alumno_id))
            elif legajo:
                alumno = scope_queryset_to_school(Alumno.objects.all(), active_school).get(id_alumno=str(legajo))
            else:
                errores += 1
                continue
        except Exception:
            errores += 1
            continue

        item_raw_course = _first_scalar(it.get("curso") or "")
        item_raw_school_course_id = _first_scalar(it.get("school_course_id") or payload.get("school_course_id") or "")

        item_school_course_ref = global_school_course_ref
        curso_item = curso_global or ""
        item_course_error = None

        if item_raw_course or item_raw_school_course_id:
            item_school_course_ref, curso_item, item_course_error = resolve_course_reference(
                school=active_school,
                raw_course=item_raw_course,
                raw_school_course_id=item_raw_school_course_id,
                required=False,
            )

        if item_course_error == LEGACY_COURSE_DEPRECATED_DETAIL:
            return _err(item_course_error, 400)
        if item_course_error:
            errores += 1
            continue
        if item_school_course_ref is None and not curso_item:
            item_school_course_ref = getattr(alumno, "school_course", None)
            curso_item = (alumno.curso or "").strip()
        if not _can_manage_course_attendance(
            request.user,
            curso_item,
            school=active_school,
            school_course=item_school_course_ref or getattr(alumno, "school_course", None),
        ):
            errores += 1
            continue

        fr = it.get("fecha") or it.get("date")
        fecha = parse_date(str(fr)) if fr else (fecha_global or date_cls.today())

        tipo_asistencia = (it.get("tipo_asistencia") or it.get("tipo") or it.get("materia") or tipo_global or "").strip()
        if not tipo_asistencia:
            tipo_asistencia = "clases"

        st = _infer_estado(it)
        if st is None:
            errores += 1
            continue
        presente = bool(st.get('presente', True))
        tarde = bool(st.get('tarde', False))
        if not presente:
            tarde = False
        if presente is None:
            presente = bool(it.get("presente", True))

        try:
            prev = scope_queryset_to_school(Asistencia.objects.filter(
                alumno=alumno, fecha=fecha, tipo_asistencia=tipo_asistencia
            ), active_school).first()
            obj, _created = scope_queryset_to_school(Asistencia.objects.all(), active_school).update_or_create(
                alumno=alumno,
                fecha=fecha,
                tipo_asistencia=tipo_asistencia,
                # ✅ NUEVO: persiste también "tarde" (si no es presente, se fuerza False arriba)
                defaults={"school": getattr(alumno, "school", None) or active_school, "presente": bool(presente), "tarde": bool(tarde)},
            )
            key_tipo = str(tipo_asistencia or "clases")
            if key_tipo not in afectados_ids_por_tipo:
                afectados_ids_por_tipo[key_tipo] = set()
            afectados_ids_por_tipo[key_tipo].add(int(alumno.id))
            guardadas += 1
            if (prev is None and (not bool(presente))) or (prev is not None and bool(prev.presente) and (not bool(presente))):
                try:
                    _notify_inasistencias_bulk(
                        alumno_ids=[alumno.id],
                        fecha=fecha,
                        tipo_asistencia=tipo_asistencia,
                        actor=getattr(request, "user", None),
                        school=active_school,
                    )
                except Exception:
                    pass
            if return_items:
                items_out.append(_serialize_asistencia_item(obj, alumno=alumno, school=active_school))
        except Exception:
            errores += 1

    if getattr(settings, "ALERTAS_INASISTENCIAS_SYNC_EN_GUARDADO", False):
        try:
            for tipo_eval, ids_eval in afectados_ids_por_tipo.items():
                evaluar_alertas_inasistencia_por_alumnos(
                    alumno_ids=sorted(ids_eval),
                    tipo_asistencia=tipo_eval,
                    actor=getattr(request, "user", None),
                )
        except Exception:
            pass

    return _ok_response({
        "guardadas": guardadas,
        "errores": errores,
        "items": items_out if return_items else [],
    })


# =========================================================
#  Justificar inasistencia / tardanza
# =========================================================
@api_view(["GET", "PATCH", "POST", "PUT"])  # GET para debug/compat + PATCH preferido, POST/PUT compat
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def justificar_asistencia(request, pk: int):
    """
    Marca una asistencia como justificada o no justificada.

    Body JSON:
      { "justificada": true/false }
    """
    # 🔒 Permiso: SOLO Preceptor (o admin) puede justificar.
    if not _can_justify(getattr(request, "user", None)):
        return _err("No tenés permisos para justificar asistencias.", status=403)

    # GET: devolvemos estado actual (útil para debug y para clientes que quieran refrescar)
    active_school = get_request_school(request)

    if request.method == "GET":
        try:
            obj = _asistencia_base_qs(active_school).get(pk=pk)
        except Asistencia.DoesNotExist:
            return _err("Asistencia no encontrada.", status=404)

        # Permisos por curso
        curso = getattr(obj.alumno, "curso", None)
        if not _can_manage_course_attendance(
            request.user,
            curso,
            school=active_school,
            school_course=getattr(obj.alumno, "school_course", None),
        ):
            return _err("No tenés permisos para ese curso.", status=403)

        falta_valor = 0.0 if bool(getattr(obj, "justificada", False)) else (
            1.0 if (not bool(obj.presente)) else (0.5 if bool(getattr(obj, "tarde", False)) else 0.0)
        )

        return _ok_response({
            "id": obj.id,
            "alumno_id": obj.alumno_id,
            "fecha": str(obj.fecha),
            "tipo_asistencia": obj.tipo_asistencia,
            "presente": bool(obj.presente),
            "tarde": bool(getattr(obj, "tarde", False)),
            "justificada": bool(getattr(obj, "justificada", False)),
            "firmada": bool(getattr(obj, "firmada", False)),
            "firmada_en": obj.firmada_en.isoformat() if getattr(obj, "firmada_en", None) else None,
            "falta_valor": falta_valor,
        })

    # Parseo JSON flexible
    data = _coerce_json(request)
    if not isinstance(data, dict):
        data = {}

    val = data.get("justificada", None)
    b = _norm_bool(val)
    if b is None:
        # toggle si no mandan valor
        b = None

    try:
        obj = _asistencia_base_qs(active_school).get(pk=pk)
    except Asistencia.DoesNotExist:
        return _err("Asistencia no encontrada.", status=404)

    # Permisos por curso
    curso = getattr(obj.alumno, "curso", None)
    if not _can_manage_course_attendance(
        request.user,
        curso,
        school=active_school,
        school_course=getattr(obj.alumno, "school_course", None),
    ):
        return _err("No tenés permisos para ese curso.", status=403)

    # Solo tiene sentido justificar si es Ausente o Tarde
    es_presente = bool(obj.presente) and (not bool(getattr(obj, "tarde", False)))
    if es_presente:
        return _err("No se puede justificar un presente.", status=400)

    nueva = (not bool(getattr(obj, "justificada", False))) if b is None else bool(b)

    setattr(obj, "justificada", nueva)
    obj.save(update_fields=["justificada"])
    if getattr(settings, "ALERTAS_INASISTENCIAS_SYNC_EN_GUARDADO", False):
        try:
            evaluar_alerta_inasistencia(
                alumno=obj.alumno,
                tipo_asistencia=getattr(obj, "tipo_asistencia", "clases"),
                actor=getattr(request, "user", None),
                asistencia=obj,
            )
        except Exception:
            pass

    falta_valor = 0.0 if nueva else (1.0 if (not bool(obj.presente)) else (0.5 if bool(getattr(obj, "tarde", False)) else 0.0))

    return _ok_response({
        "id": obj.id,
        "alumno_id": obj.alumno_id,
        "fecha": str(obj.fecha),
        "tipo_asistencia": obj.tipo_asistencia,
        "presente": bool(obj.presente),
        "tarde": bool(getattr(obj, "tarde", False)),
        "justificada": bool(getattr(obj, "justificada", False)),
        "firmada": bool(getattr(obj, "firmada", False)),
        "firmada_en": obj.firmada_en.isoformat() if getattr(obj, "firmada_en", None) else None,
        "falta_valor": falta_valor,
    })


@api_view(["GET", "POST", "PATCH"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def firmar_asistencia(request, pk: int):
    active_school = get_request_school(request)
    try:
        obj = _asistencia_base_qs(active_school).get(pk=pk)
    except Asistencia.DoesNotExist:
        return _err("Asistencia no encontrada.", status=404)

    if not _can_sign_asistencia(getattr(request, "user", None), obj.alumno):
        return _err("No tenés permisos para firmar esta asistencia.", status=403)

    if request.method == "GET":
        return _ok_response({
            "id": obj.id,
            "alumno_id": obj.alumno_id,
            "fecha": str(obj.fecha),
            "tipo_asistencia": obj.tipo_asistencia,
            "firmada": bool(getattr(obj, "firmada", False)),
            "firmada_en": obj.firmada_en.isoformat() if getattr(obj, "firmada_en", None) else None,
        })

    es_presente = bool(obj.presente) and (not bool(getattr(obj, "tarde", False)))
    if es_presente:
        return _err("No se puede firmar un presente.", 400)

    if bool(getattr(obj, "firmada", False)):
        return _err(
            "La inasistencia ya fue firmada.",
            400,
            {
                "id": obj.id,
                "alumno_id": obj.alumno_id,
                "firmada": True,
                "firmada_en": obj.firmada_en.isoformat() if getattr(obj, "firmada_en", None) else None,
            },
        )

    obj.firmada = True
    obj.firmada_en = timezone.now()
    obj.firmada_por = request.user
    obj.save(update_fields=["firmada", "firmada_en", "firmada_por"])

    return _ok_response({
        "id": obj.id,
        "alumno_id": obj.alumno_id,
        "fecha": str(obj.fecha),
        "tipo_asistencia": obj.tipo_asistencia,
        "firmada": True,
        "firmada_en": obj.firmada_en.isoformat() if obj.firmada_en else None,
    })


# =========================================================
#  Listados (GET)
# =========================================================
# =========================================================
#  Editar detalle (observación) de una asistencia
# =========================================================
@api_view(["GET", "PATCH", "POST", "PUT"])  # GET para leer; PATCH preferido; POST/PUT compat
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def editar_detalle_asistencia(request, pk: int):
    """
    Permite a un preceptor (o admin) cargar/editar el detalle (observación) de una asistencia.

    Body JSON (cualquiera de estas keys):
      { "detalle": "..." }  | { "observacion": "..." } | { "observaciones": "..." }

    Respuesta:
      { id, observacion, detalle, ... }
    """
    active_school = get_request_school(request)
    try:
        obj = _asistencia_base_qs(active_school).get(pk=pk)
    except Asistencia.DoesNotExist:
        return _err("Asistencia no encontrada.", status=404)

    if not _can_edit_asistencia_detalle(getattr(request, "user", None), obj.alumno):
        return _err("No tenés permisos para editar el detalle de asistencias.", status=403)

    # Permisos por curso (mismo criterio que justificar)
    curso = getattr(obj.alumno, "curso", None)
    if not _can_manage_course_attendance(
        request.user,
        curso,
        school=active_school,
        school_course=getattr(obj.alumno, "school_course", None),
    ):
        return _err("No tenés permisos para ese curso.", status=403)

    if request.method == "GET":
        return _ok_response({
            "id": obj.id,
            "alumno_id": obj.alumno_id,
            "fecha": str(obj.fecha),
            "tipo_asistencia": obj.tipo_asistencia,
            "presente": bool(obj.presente),
            "tarde": bool(getattr(obj, "tarde", False)),
            "justificada": bool(getattr(obj, "justificada", False)),
            "observacion": getattr(obj, "observacion", "") or "",
            "detalle": getattr(obj, "observacion", "") or "",
        })

    body = _coerce_json(request)
    raw = (
        body.get("detalle")
        if body.get("detalle") is not None
        else body.get("observacion")
        if body.get("observacion") is not None
        else body.get("observaciones")
        if body.get("observaciones") is not None
        else body.get("comentario")
    )

    if raw is None:
        return _err("Falta 'detalle' (o 'observacion').", status=400)

    detalle = str(raw).strip()

    # límite razonable por si el front manda cualquier cosa
    if len(detalle) > 255:
        detalle = detalle[:255]

    setattr(obj, "observacion", detalle)
    obj.save(update_fields=["observacion"])

    return _ok_response({
        "id": obj.id,
        "alumno_id": obj.alumno_id,
        "fecha": str(obj.fecha),
        "tipo_asistencia": obj.tipo_asistencia,
        "presente": bool(obj.presente),
        "tarde": bool(getattr(obj, "tarde", False)),
        "justificada": bool(getattr(obj, "justificada", False)),
        "observacion": getattr(obj, "observacion", "") or "",
        "detalle": getattr(obj, "observacion", "") or "",
    })


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def asistencias_por_alumno(request, alumno_id=None):
    """GET:
    - /api/asistencias/alumno/<int:alumno_id>/
    - /api/asistencias/?alumno=<id> / ?alumno_id=<id>
    - /api/asistencias/?id_alumno=<legajo>
    """
    active_school = get_request_school(request)
    aid = alumno_id or request.GET.get("alumno") or request.GET.get("alumno_id")
    codigo = request.GET.get("id_alumno") or request.GET.get("legajo")

    alumno = None
    if aid:
        try:
            alumno = _alumno_base_qs(active_school).get(pk=int(aid))
        except Exception:
            alumno = None
    if alumno is None and codigo:
        try:
            alumno = _alumno_base_qs(active_school).get(id_alumno=str(codigo))
        except Exception:
            alumno = None

    if alumno is None:
        return Response({"detail": "Alumno no encontrado"}, status=404)

    if not _can_view_alumno_asistencia(request.user, alumno):
        return Response({"detail": "No autorizado."}, status=403)

    qs = _asistencia_base_qs(active_school).filter(alumno=alumno).order_by("-fecha", "-id")

    results = []
    for a in qs:
        results.append(_serialize_asistencia_item(a, alumno=alumno, school=active_school))

    return Response({
        "alumno": _serialize_alumno_brief(alumno, school=active_school),
        "results": results,
        "count": len(results),
    })


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def asistencias_por_codigo(request, id_alumno):
    active_school = get_request_school(request)
    try:
        alumno = _alumno_base_qs(active_school).get(id_alumno=str(id_alumno))
    except Exception:
        return Response({"detail": "Alumno no encontrado"}, status=404)
    return asistencias_por_alumno(request, alumno_id=alumno.id)


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def asistencias_por_curso_y_fecha(request):
    """
    GET /api/asistencias/curso/?school_course_id=14&fecha=YYYY-MM-DD&tipo=informatica
    Requiere school_course_id para seleccionar curso.
    """
    active_school = get_request_school(request)
    school_course_ref, curso, course_error = resolve_course_reference(
        school=active_school,
        raw_course=request.GET.get("curso"),
        raw_school_course_id=request.GET.get("school_course_id"),
        required=True,
    )
    fecha = parse_date(str(request.GET.get("fecha") or "")) if request.GET.get("fecha") else None
    tipo = (request.GET.get("tipo") or request.GET.get("tipo_asistencia") or request.GET.get("materia") or "").strip()

    if course_error:
        return Response({"detail": course_error}, status=400)
    if active_school is not None and school_course_ref is None:
        return Response({"detail": "No existe ese curso en el colegio activo."}, status=400)
    if not curso or not fecha:
        return Response({"detail": "Faltan curso y/o fecha"}, status=400)

    if not _can_manage_course_attendance(
        request.user,
        curso,
        school=active_school,
        school_course=school_course_ref,
    ):
        return Response({"detail": "No tenés permisos para ese curso."}, status=403)

    alumnos = _alumnos_por_curso_qs(
        curso,
        school=active_school,
        school_course=school_course_ref,
    )
    qs = scope_queryset_to_school(Asistencia.objects.filter(alumno__in=alumnos, fecha=fecha), active_school)
    if tipo:
        qs = qs.filter(tipo_asistencia=tipo)

    items = []
    for a in qs.select_related("alumno", "alumno__school_course"):
        items.append(_serialize_asistencia_item(a, curso=curso, school=active_school))

    response_payload = {
        "curso_label": _curso_label(curso, school=active_school),
        "fecha": str(fecha),
        "tipo_asistencia": tipo or None,
        "items": items,
    }
    response_payload.update(
        _public_course_payload(school_course=school_course_ref, curso=curso, school=active_school)
    )
    return Response(response_payload)
