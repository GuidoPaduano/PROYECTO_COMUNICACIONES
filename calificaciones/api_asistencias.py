# calificaciones/api_asistencias.py
from __future__ import annotations

from datetime import date as date_cls
import json
from typing import Any, Dict, List, Optional

from django.utils.dateparse import parse_date
from django.db import transaction
from django.contrib.auth import get_user_model
from django.db.models import Q

from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    parser_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import Alumno, Asistencia, Notificacion
from .utils_cursos import filtrar_cursos_validos

try:
    # Si existen los modelos reales de preceptor/profesor → cursos
    from .models_preceptores import PreceptorCurso, ProfesorCurso  # type: ignore
except Exception:
    PreceptorCurso = None
    ProfesorCurso = None


# =========================================================
# Roles / permisos
# =========================================================
def _user_in_group(user, *names: str) -> bool:
    """True si el usuario pertenece a alguno de los grupos indicados."""
    try:
        wanted = {str(n).strip() for n in names if str(n).strip()}
        if not wanted:
            return False
        user_groups = {g.name.strip() for g in user.groups.all()}
        return bool(wanted.intersection(user_groups))
    except Exception:
        return False


def _can_justify(user) -> bool:
    """Solo Preceptores (y superuser/staff) pueden justificar."""
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True
    # En el proyecto aparecen ambos nombres en distintos lugares
    return _user_in_group(user, "Preceptores", "Preceptor")


# =========================================================
# Helpers
# =========================================================
def _has_model_field(model, name: str) -> bool:
    try:
        model._meta.get_field(name)
        return True
    except Exception:
        return False


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

            # Si es un QueryDict-like
            if hasattr(data, "keys") and hasattr(data, "get"):
                out: Dict[str, Any] = {}
                for k in list(data.keys()):
                    out[k] = _first_scalar(data.get(k))
                return out

            # Si ya es dict normal
            if isinstance(data, dict):
                out = {}
                for k, v in data.items():
                    out[k] = _first_scalar(v)
                return out
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
    _add(getattr(alumno, "usuario", None))

    try:
        legajo = (getattr(alumno, "id_alumno", "") or "").strip()
        if legajo:
            if legajo_user_map is not None:
                _add(legajo_user_map.get(legajo))
            else:
                User = get_user_model()
                _add(User.objects.filter(username__iexact=legajo).first())
    except Exception:
        pass

    return destinatarios


def _notify_inasistencias_bulk(*, alumno_ids: List[int], fecha, tipo_asistencia: str, actor=None):
    if not alumno_ids:
        return 0
    try:
        qs = Alumno.objects.filter(id__in=alumno_ids).select_related("padre", "usuario")
    except Exception:
        qs = Alumno.objects.filter(id__in=alumno_ids)

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

        titulo = f"Inasistencia registrada: {alumno_nombre}"
        desc_parts = [f"Alumno: {alumno_nombre}"]
        if getattr(a, "curso", ""):
            desc_parts.append(f"Curso: {a.curso}")
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
                    destinatario=dest,
                    tipo="inasistencia",
                    titulo=titulo,
                    descripcion=descripcion,
                    url=f"/alumnos/{getattr(a, 'id', '')}/?tab=asistencias",
                    leida=False,
                    meta={
                        "alumno_id": getattr(a, "id", None),
                        "alumno_legajo": getattr(a, "id_alumno", None),
                        "curso": getattr(a, "curso", ""),
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


def _cursos_choices() -> List[tuple[str, str]]:
    base = filtrar_cursos_validos(getattr(Alumno, "CURSOS", []))
    return list(base)


def _tipo_choices() -> List[tuple[str, str]]:
    return list(getattr(Asistencia, "TIPO_ASISTENCIA", []))


def _curso_label(curso: str) -> str:
    return dict(_cursos_choices()).get(curso, curso)


def _tipo_label(tipo_asistencia: str) -> str:
    return dict(_tipo_choices()).get(tipo_asistencia, tipo_asistencia)


def obtener_curso_del_preceptor(usuario) -> Optional[str]:
    """Fallback dev simple (si no existe PreceptorCurso)."""
    cursos_por_usuario = {
        "preceptor1": "1A",
        "preceptor2": "3B",
        "preceptor3": "5NAT",
    }
    return cursos_por_usuario.get(getattr(usuario, "username", ""), None)


def _cursos_de_usuario(user) -> List[str]:
    """Cursos permitidos para el usuario."""
    todos = [c[0] for c in _cursos_choices()]

    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return todos

    asignados: List[str] = []

    if PreceptorCurso is not None:
        try:
            asignados = list(
                PreceptorCurso.objects.filter(preceptor=user)
                .values_list("curso", flat=True)
                .distinct()
            )
        except Exception:
            asignados = []

    if ProfesorCurso is not None:
        try:
            asignados_prof = list(
                ProfesorCurso.objects.filter(profesor=user)
                .values_list("curso", flat=True)
                .distinct()
            )
            asignados = list(set(asignados) | set(asignados_prof))
        except Exception:
            pass

    if not asignados:
        c = obtener_curso_del_preceptor(user)
        if c:
            asignados = [c]

    if not asignados:
        try:
            grupos = {g.name.strip() for g in user.groups.all()}
            if "Profesores" in grupos or "Profesor" in grupos:
                return todos
            asignados = [c for c in todos if c in grupos]
        except Exception:
            asignados = []

    validos = set(todos)
    return sorted([c for c in asignados if c in validos])


def _ok_response(payload: Dict[str, Any], status: int = 200) -> Response:
    """✅ Siempre devolvemos ok + success + message para compat con front."""
    if "ok" not in payload:
        payload["ok"] = True
    if "success" not in payload:
        payload["success"] = bool(payload.get("ok"))
    if "message" not in payload:
        payload["message"] = "Asistencia guardada ✅" if payload.get("ok") else "Error"
    return Response(payload, status=status)


def _err(detail: str, status: int = 400, extra: Optional[Dict[str, Any]] = None) -> Response:
    payload = {"ok": False, "success": False, "detail": detail}
    if extra:
        payload.update(extra)
    return Response(payload, status=status)


def _bulk_upsert_asistencias(
    alumno_ids: List[int],
    fecha,
    tipo_asistencia: str,
    estado_by_alumno_id: Dict[int, Dict[str, bool]],
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
        Asistencia.objects.filter(
            alumno_id__in=alumno_ids,
            fecha=fecha,
            tipo_asistencia=tipo_asistencia,
        )
    )
    by_aid = {a.alumno_id: a for a in existentes}

    to_update: List[Asistencia] = []
    to_create: List[Asistencia] = []
    ausentes: List[int] = []

    for aid in alumno_ids:
        st = estado_by_alumno_id.get(aid) or {"presente": True, "tarde": False}
        presente = bool(st.get("presente", True))
        tarde = bool(st.get("tarde", False))
        if not presente:
            tarde = False

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
            if changed:
                to_update.append(obj)
                if prev_presente and (not presente):
                    ausentes.append(aid)
        else:
            to_create.append(
                Asistencia(
                    alumno_id=aid,
                    fecha=fecha,
                    tipo_asistencia=tipo_asistencia,
                    presente=presente,
                    tarde=tarde,
                )
            )
            if not presente:
                ausentes.append(aid)

    with transaction.atomic():
        if to_update:
            Asistencia.objects.bulk_update(to_update, ["presente", "tarde"])
        if to_create:
            try:
                Asistencia.objects.bulk_create(to_create, batch_size=500)
            except Exception:
                for obj in to_create:
                    Asistencia.objects.update_or_create(
                        alumno_id=obj.alumno_id,
                        fecha=obj.fecha,
                        tipo_asistencia=obj.tipo_asistencia,
                        defaults={"presente": bool(obj.presente), "tarde": bool(getattr(obj, "tarde", False)), "justificada": False},
                    )

    return {"guardadas": len(alumno_ids), "errores": 0, "ausentes": ausentes}


# =========================================================
#  Preceptor: cursos
# =========================================================
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def preceptor_cursos(request):
    cursos = _cursos_de_usuario(request.user)
    data = [{"curso": c, "nombre": _curso_label(c)} for c in cursos]
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
    payload = _coerce_json(request)

    # ✅ NUEVO: por defecto NO devolvemos items (para que sea rápido y no pese)
    return_items = _norm_bool(payload.get("return_items"))
    if return_items is None:
        return_items = False

    # -----------------------------------------------------
    # Formato C: mapping id->bool
    #   {curso, fecha, tipo_asistencia|tipo, asistencias:{ "418": true, ... }}
    # -----------------------------------------------------
    if isinstance(payload, dict) and ("asistencias" in payload or "asistenciasPayload" in payload):
        raw_map = payload.get("asistencias", payload.get("asistenciasPayload"))
        raw_map = _try_parse_json(raw_map)

        if isinstance(raw_map, dict):
            curso = str(_first_scalar(payload.get("curso") or "") or "").strip()
            tipo_asistencia = str(
                _first_scalar(payload.get("tipo_asistencia") or payload.get("tipo") or payload.get("materia") or "") or ""
            ).strip()

            fecha_raw = _first_scalar(payload.get("fecha") or payload.get("date"))
            fecha = parse_date(str(fecha_raw)) if fecha_raw else date_cls.today()

            if not curso:
                return _err("Falta curso", 400)
            if not tipo_asistencia:
                return _err("Falta tipo_asistencia/tipo", 400)

            permitidos = _cursos_de_usuario(request.user)
            if permitidos and (curso not in permitidos):
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

            alumnos_qs = Alumno.objects.filter(curso=curso).filter(
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
                res = _bulk_upsert_asistencias(alumno_ids, fecha, tipo_asistencia, estado_by_id)
            except Exception:
                return _err("Error guardando asistencias (bulk).", 500)

            try:
                _notify_inasistencias_bulk(
                    alumno_ids=sorted(set(res.get("ausentes") or [])),
                    fecha=fecha,
                    tipo_asistencia=tipo_asistencia,
                    actor=getattr(request, "user", None),
                )
            except Exception:
                pass

            items_out: List[Dict[str, Any]] = []
            if return_items and alumno_ids:
                qs = Asistencia.objects.filter(
                    alumno_id__in=alumno_ids,
                    fecha=fecha,
                    tipo_asistencia=tipo_asistencia,
                ).select_related("alumno")
                for obj in qs:
                    items_out.append({
                        "id": obj.id,
                        "alumno_id": obj.alumno_id,
                        "id_alumno": getattr(obj.alumno, "id_alumno", None),
                        "fecha": str(obj.fecha),
                        "curso": getattr(obj.alumno, "curso", curso),
                        "tipo_asistencia": obj.tipo_asistencia,
                        "tipo_label": _tipo_label(obj.tipo_asistencia),
                        "presente": bool(obj.presente),
                        "tarde": bool(getattr(obj, "tarde", False)),
                        # ✅ NUEVO: equivalente de falta (Ausente=1, Tarde=0.5, Presente=0)
                        "falta_valor": 0.0 if bool(getattr(obj, "justificada", False)) else (1.0 if (not bool(obj.presente)) else (0.5 if bool(getattr(obj, "tarde", False)) else 0.0)),
                        "observacion": getattr(obj, "observacion", "") or "",
                    })

            return _ok_response({
                "curso": curso,
                "fecha": str(fecha),
                "tipo_asistencia": tipo_asistencia,
                "guardadas": res.get("guardadas", 0),
                "errores": int(errores) + int(res.get("errores", 0)),
                "items": items_out if return_items else [],
            })

    # -----------------------------------------------------
    # Formato A: presentes por curso (lista de IDs)
    #   {curso, fecha, tipo_asistencia|tipo, presentes:[ids]}
    # -----------------------------------------------------
    if isinstance(payload, dict) and (
        "presentes" in payload or "presentes_ids" in payload or "presentesId" in payload
    ):
        curso = str(_first_scalar(payload.get("curso") or "") or "").strip()
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

        if not curso:
            return _err("Falta curso", 400)
        if not tipo_asistencia:
            return _err("Falta tipo_asistencia/tipo", 400)

        permitidos = _cursos_de_usuario(request.user)
        if permitidos and (curso not in permitidos):
            return _err("No tenés permisos para ese curso.", 403)

        alumno_ids = list(Alumno.objects.filter(curso=curso).values_list("id", flat=True))
        if not alumno_ids:
            return _ok_response({
                "curso": curso,
                "fecha": str(fecha),
                "tipo_asistencia": tipo_asistencia,
                "guardadas": 0,
                "errores": 0,
                "items": [],
            })

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
            res = _bulk_upsert_asistencias(alumno_ids, fecha, tipo_asistencia, estado_by_id)
        except Exception:
            return _err("Error guardando asistencias (bulk).", 500)

        try:
            _notify_inasistencias_bulk(
                alumno_ids=sorted(set(res.get("ausentes") or [])),
                fecha=fecha,
                tipo_asistencia=tipo_asistencia,
                actor=getattr(request, "user", None),
            )
        except Exception:
            pass

        items_out: List[Dict[str, Any]] = []
        if return_items:
            qs = Asistencia.objects.filter(
                alumno_id__in=alumno_ids,
                fecha=fecha,
                tipo_asistencia=tipo_asistencia,
            ).select_related("alumno")
            for obj in qs:
                items_out.append({
                    "id": obj.id,
                    "alumno_id": obj.alumno_id,
                    "id_alumno": getattr(obj.alumno, "id_alumno", None),
                    "fecha": str(obj.fecha),
                    "curso": getattr(obj.alumno, "curso", curso),
                    "tipo_asistencia": obj.tipo_asistencia,
                    "tipo_label": _tipo_label(obj.tipo_asistencia),
                    "presente": bool(obj.presente),
                    "tarde": bool(getattr(obj, "tarde", False)),
                    "justificada": bool(getattr(obj, "justificada", False)),
                        "falta_valor": 0.0 if bool(getattr(obj, "justificada", False)) else (1.0 if (not bool(obj.presente)) else (0.5 if bool(getattr(obj, "tarde", False)) else 0.0)),
                    "observacion": getattr(obj, "observacion", "") or "",
                })

        return _ok_response({
            "curso": curso,
            "fecha": str(fecha),
            "tipo_asistencia": tipo_asistencia,
            "guardadas": res.get("guardadas", 0),
            "errores": res.get("errores", 0),
            "items": items_out if return_items else [],
        })

    # -----------------------------------------------------
    # Formato B: items (legacy)
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
        curso_global = str(_first_scalar(payload.get("curso") or "") or "").strip() or None

    guardadas = 0
    errores = 0
    items_out: List[Dict[str, Any]] = []

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
                alumno = Alumno.objects.get(pk=int(alumno_id))
            elif legajo:
                alumno = Alumno.objects.get(id_alumno=str(legajo))
            else:
                errores += 1
                continue
        except Exception:
            errores += 1
            continue

        curso_item = (it.get("curso") or curso_global or alumno.curso or "").strip()
        permitidos = _cursos_de_usuario(request.user)
        if permitidos and curso_item and (curso_item not in permitidos):
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
            prev = Asistencia.objects.filter(
                alumno=alumno, fecha=fecha, tipo_asistencia=tipo_asistencia
            ).first()
            obj, _created = Asistencia.objects.update_or_create(
                alumno=alumno,
                fecha=fecha,
                tipo_asistencia=tipo_asistencia,
                # ✅ NUEVO: persiste también "tarde" (si no es presente, se fuerza False arriba)
                defaults={"presente": bool(presente), "tarde": bool(tarde)},
            )
            guardadas += 1
            if (prev is None and (not bool(presente))) or (prev is not None and bool(prev.presente) and (not bool(presente))):
                try:
                    _notify_inasistencias_bulk(
                        alumno_ids=[alumno.id],
                        fecha=fecha,
                        tipo_asistencia=tipo_asistencia,
                        actor=getattr(request, "user", None),
                    )
                except Exception:
                    pass
            if return_items:
                items_out.append({
                    "id": obj.id,
                    "alumno_id": alumno.id,
                    "id_alumno": alumno.id_alumno,
                    "fecha": str(obj.fecha),
                    "curso": alumno.curso,
                    "tipo_asistencia": obj.tipo_asistencia,
                    "tipo_label": _tipo_label(obj.tipo_asistencia),
                    "presente": bool(obj.presente),
                    "tarde": bool(getattr(obj, "tarde", False)),
                    "justificada": bool(getattr(obj, "justificada", False)),
                        "falta_valor": 0.0 if bool(getattr(obj, "justificada", False)) else (1.0 if (not bool(obj.presente)) else (0.5 if bool(getattr(obj, "tarde", False)) else 0.0)),
                    "observacion": getattr(obj, "observacion", "") or "",
                })
        except Exception:
            errores += 1

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
    if request.method == "GET":
        try:
            obj = Asistencia.objects.select_related("alumno").get(pk=pk)
        except Asistencia.DoesNotExist:
            return _err("Asistencia no encontrada.", status=404)

        # Permisos por curso
        curso = getattr(obj.alumno, "curso", None)
        permitidos = _cursos_de_usuario(request.user)
        if curso and permitidos and (curso not in permitidos):
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
        obj = Asistencia.objects.select_related("alumno").get(pk=pk)
    except Asistencia.DoesNotExist:
        return _err("Asistencia no encontrada.", status=404)

    # Permisos por curso
    curso = getattr(obj.alumno, "curso", None)
    permitidos = _cursos_de_usuario(request.user)
    if curso and permitidos and (curso not in permitidos):
        return _err("No tenés permisos para ese curso.", status=403)

    # Solo tiene sentido justificar si es Ausente o Tarde
    es_presente = bool(obj.presente) and (not bool(getattr(obj, "tarde", False)))
    if es_presente:
        return _err("No se puede justificar un presente.", status=400)

    nueva = (not bool(getattr(obj, "justificada", False))) if b is None else bool(b)

    setattr(obj, "justificada", nueva)
    obj.save(update_fields=["justificada"])

    falta_valor = 0.0 if nueva else (1.0 if (not bool(obj.presente)) else (0.5 if bool(getattr(obj, "tarde", False)) else 0.0))

    return _ok_response({
        "id": obj.id,
        "alumno_id": obj.alumno_id,
        "fecha": str(obj.fecha),
        "tipo_asistencia": obj.tipo_asistencia,
        "presente": bool(obj.presente),
        "tarde": bool(getattr(obj, "tarde", False)),
        "justificada": bool(getattr(obj, "justificada", False)),
        "falta_valor": falta_valor,
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
    # 🔒 Permiso: SOLO Preceptor (o admin)
    if not _can_justify(getattr(request, "user", None)):
        return _err("No tenés permisos para editar el detalle de asistencias.", status=403)

    try:
        obj = Asistencia.objects.select_related("alumno").get(pk=pk)
    except Asistencia.DoesNotExist:
        return _err("Asistencia no encontrada.", status=404)

    # Permisos por curso (mismo criterio que justificar)
    curso = getattr(obj.alumno, "curso", None)
    permitidos = _cursos_de_usuario(request.user)
    if curso and permitidos and (curso not in permitidos):
        return _err("No tenés permisos para ese curso.", status=403)

    # Solo tiene sentido editar detalle si es Ausente o Tarde
    es_presente = bool(obj.presente) and (not bool(getattr(obj, "tarde", False)))
    if es_presente:
        return _err("Solo se puede cargar detalle en ausentes o tardanzas.", status=400)

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
    aid = alumno_id or request.GET.get("alumno") or request.GET.get("alumno_id")
    codigo = request.GET.get("id_alumno") or request.GET.get("legajo")

    alumno = None
    if aid:
        try:
            alumno = Alumno.objects.get(pk=int(aid))
        except Exception:
            alumno = None
    if alumno is None and codigo:
        try:
            alumno = Alumno.objects.get(id_alumno=str(codigo))
        except Exception:
            alumno = None

    if alumno is None:
        return Response({"detail": "Alumno no encontrado"}, status=404)

    qs = Asistencia.objects.filter(alumno=alumno).order_by("-fecha", "-id")

    results = []
    for a in qs:
        results.append({
            "id": a.id,
            "alumno_id": alumno.id,
            "id_alumno": alumno.id_alumno,
            "fecha": str(a.fecha),
            "curso": alumno.curso,
            "tipo_asistencia": a.tipo_asistencia,
            "tipo_label": _tipo_label(a.tipo_asistencia),
            "presente": bool(a.presente),
            "tarde": bool(getattr(a, "tarde", False)),
            "justificada": bool(getattr(a, "justificada", False)),
            "falta_valor": 0.0 if bool(getattr(a, "justificada", False)) else (1.0 if (not bool(a.presente)) else (0.5 if bool(getattr(a, "tarde", False)) else 0.0)),
            "observacion": getattr(a, "observacion", "") or "",
        })

    return Response({
        "alumno": {"id": alumno.id, "id_alumno": alumno.id_alumno, "nombre": alumno.nombre, "curso": alumno.curso},
        "results": results,
        "count": len(results),
    })


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def asistencias_por_codigo(request, id_alumno):
    try:
        alumno = Alumno.objects.get(id_alumno=str(id_alumno))
    except Exception:
        return Response({"detail": "Alumno no encontrado"}, status=404)
    return asistencias_por_alumno(request, alumno_id=alumno.id)


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def asistencias_por_curso_y_fecha(request):
    """GET /api/asistencias/curso/?curso=1A&fecha=YYYY-MM-DD&tipo=informatica"""
    curso = (request.GET.get("curso") or "").strip()
    fecha = parse_date(str(request.GET.get("fecha") or "")) if request.GET.get("fecha") else None
    tipo = (request.GET.get("tipo") or request.GET.get("tipo_asistencia") or request.GET.get("materia") or "").strip()

    if not curso or not fecha:
        return Response({"detail": "Faltan curso y/o fecha"}, status=400)

    permitidos = _cursos_de_usuario(request.user)
    if permitidos and (curso not in permitidos):
        return Response({"detail": "No tenés permisos para ese curso."}, status=403)

    alumnos = Alumno.objects.filter(curso=curso).order_by("nombre")
    qs = Asistencia.objects.filter(alumno__in=alumnos, fecha=fecha)
    if tipo:
        qs = qs.filter(tipo_asistencia=tipo)

    items = []
    for a in qs.select_related("alumno"):
        items.append({
            "id": a.id,
            "alumno_id": a.alumno_id,
            "id_alumno": getattr(a.alumno, "id_alumno", None),
            "fecha": str(a.fecha),
            "curso": getattr(a.alumno, "curso", curso),
            "tipo_asistencia": a.tipo_asistencia,
            "tipo_label": _tipo_label(a.tipo_asistencia),
            "presente": bool(a.presente),
            "tarde": bool(getattr(a, "tarde", False)),
            "justificada": bool(getattr(a, "justificada", False)),
            "falta_valor": 0.0 if bool(getattr(a, "justificada", False)) else (1.0 if (not bool(a.presente)) else (0.5 if bool(getattr(a, "tarde", False)) else 0.0)),
            "observacion": getattr(a, "observacion", "") or "",
        })

    return Response({
        "curso": curso,
        "curso_label": _curso_label(curso),
        "fecha": str(fecha),
        "tipo_asistencia": tipo or None,
        "items": items,
    })
