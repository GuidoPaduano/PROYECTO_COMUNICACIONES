# calificaciones/api_mensajes/_helpers.py
from django.core.exceptions import FieldDoesNotExist
from django.utils import timezone
from django.db import models
from django.contrib.auth import get_user_model

from ..course_access import build_course_membership_q, course_ref_matches, get_assignment_course_refs
from ..models import Alumno, Mensaje, Notificacion, resolve_school_course_for_value
from ..resend_email import send_message_email
from ..schools import get_request_school, scope_queryset_to_school
from ..user_groups import get_user_group_names_lower, user_has_group_fragment, user_in_groups
from ..utils_cursos import resolve_course_reference

from uuid import UUID, uuid4
import json
import re
from functools import lru_cache

User = get_user_model()

try:
    from ..models_preceptores import PreceptorCurso, ProfesorCurso  # type: ignore
except Exception:
    PreceptorCurso = None
    ProfesorCurso = None

# ===================== Performance knobs =====================
DEFAULT_CONV_LIMIT = 50
MAX_CONV_LIMIT = 300


# ===================== Helpers =====================
def _has_field(model, field_name: str) -> bool:
    try:
        model._meta.get_field(field_name)
        return True
    except FieldDoesNotExist:
        return False


@lru_cache(maxsize=1)
def _sender_field() -> str:
    """Compat: Mensaje.remitente (nuevo) vs Mensaje.emisor (viejo)."""
    return "remitente" if _has_field(Mensaje, "remitente") else "emisor"


@lru_cache(maxsize=1)
def _recipient_field() -> str:
    """Compat: Mensaje.destinatario (nuevo) vs Mensaje.receptor (viejo)."""
    return "destinatario" if _has_field(Mensaje, "destinatario") else "receptor"


@lru_cache(maxsize=1)
def _threads_enabled() -> bool:
    """True si el modelo Mensaje tiene thread_id."""
    return _has_field(Mensaje, "thread_id")


def _course_code_for_storage(*, school_course=None, curso=None, alumno=None) -> str:
    alumno_school_course = getattr(alumno, "school_course", None) if alumno is not None else None
    return str(
        getattr(school_course, "code", None)
        or getattr(alumno_school_course, "code", None)
        or getattr(alumno, "curso", None)
        or curso
        or ""
    ).strip()


def _alumnos_por_curso_qs(curso: str = "", *, school=None, school_course=None):
    course_code = _course_code_for_storage(school_course=school_course, curso=curso)
    if not course_code:
        return Alumno.objects.none()

    school_course = school_course or (
        resolve_school_course_for_value(school=school, curso=course_code)
        if school is not None
        else None
    )
    course_q = build_course_membership_q(
        school_course_id=getattr(school_course, "id", None),
        course_code=course_code,
        school_course_field="school_course",
        code_field="curso",
    )
    if course_q is None:
        return Alumno.objects.none()
    return scope_queryset_to_school(Alumno.objects.all(), school).filter(course_q)


@lru_cache(maxsize=1)
def _flags():
    return {
        "has_remitente": _has_field(Mensaje, "remitente"),
        "has_destinatario": _has_field(Mensaje, "destinatario"),
        "has_leido": _has_field(Mensaje, "leido"),
        "has_leido_en": _has_field(Mensaje, "leido_en"),
        "has_alumno": _has_field(Mensaje, "alumno"),
        "has_tipo": _has_field(Mensaje, "tipo"),
        "has_tipo_remitente": _has_field(Mensaje, "tipo_remitente"),
        "has_fecha_envio": _has_field(Mensaje, "fecha_envio"),
        "has_reply_to": _has_field(Mensaje, "reply_to"),
    }


def _parse_int(value, default=None):
    try:
        return int(value)
    except Exception:
        return default


def _parse_limit(request, default=DEFAULT_CONV_LIMIT):
    lim = _parse_int(request.GET.get("limit"), default)
    if lim is None:
        lim = default
    lim = max(1, min(lim, MAX_CONV_LIMIT))
    return lim


def _parse_before_id(request):
    """
    before_id: devuelve mensajes con id < before_id (útil para "cargar más hacia atrás")
    """
    return _parse_int(request.GET.get("before_id"), None)


def _normalize_subject(subject: str) -> str:
    """
    Quita cadenas repetidas de "Re:" al inicio y devuelve el asunto base.
    Ej: "Re: Re: Asunto" -> "Asunto"
    """
    s = (subject or "").strip()
    if not s:
        return ""
    # Quita prefijos repetidos tipo "Re:" (case-insensitive)
    s = re.sub(r"^(\\s*re\\s*:\\s*)+", "", s, flags=re.IGNORECASE)
    return s.strip()


def _safe_select_related(qs, *fields):
    """
    Aplica select_related si el campo existe y parece relacional.
    No rompe si el campo no existe o no es FK.
    """
    ok_fields = []
    for f in fields:
        if not f:
            continue
        try:
            mf = Mensaje._meta.get_field(f)
            # Relación (FK/OneToOne)
            if getattr(mf, "is_relation", False):
                ok_fields.append(f)
        except Exception:
            continue
    if ok_fields:
        try:
            return qs.select_related(*ok_fields)
        except Exception:
            return qs
    return qs


@lru_cache(maxsize=16)
def _message_select_related_fields(fields: tuple[str, ...]) -> tuple[str, ...]:
    ok_fields = []
    for f in fields:
        if not f:
            continue
        try:
            mf = Mensaje._meta.get_field(f)
            if getattr(mf, "is_relation", False):
                ok_fields.append(f)
        except Exception:
            continue
    return tuple(ok_fields)


def _select_message_related(qs, *fields):
    ok_fields = _message_select_related_fields(tuple(fields))
    if not ok_fields:
        return qs
    try:
        return qs.select_related(*ok_fields)
    except Exception:
        return qs


def _message_base_queryset(*, school=None):
    sf = _sender_field()
    rf = _recipient_field()
    qs = scope_queryset_to_school(Mensaje.objects.all(), school)
    return _select_message_related(qs, sf, rf, "school_course", "alumno")


def _user_label(u):
    try:
        return (u.get_full_name() or u.username) if u else ""
    except Exception:
        return getattr(u, "username", "") or ""


def _is_directivo_user(user) -> bool:
    return user_in_groups(user, "Directivos", "Directivo")


def _staff_can_send_schoolwide(user) -> bool:
    try:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False) or _is_directivo_user(user):
            return True
    except Exception:
        return False
    return False


def _message_course_refs_for_user(user, *, school=None, role: str = ""):
    school_id = getattr(school, "id", None) or 0
    cache_attr = "_cached_message_course_refs_by_scope"
    cache_key = (str(role or "").strip().lower(), school_id)
    cached = getattr(user, cache_attr, None)
    if isinstance(cached, dict) and cache_key in cached:
        return list(cached[cache_key])

    refs = []
    model = None
    user_field = ""
    if cache_key[0] == "preceptor":
        model = PreceptorCurso
        user_field = "preceptor"
    elif cache_key[0] == "profesor":
        model = ProfesorCurso
        user_field = "profesor"

    if model is not None and user_field:
        try:
            qs = scope_queryset_to_school(model.objects.filter(**{user_field: user}), school)
            refs = get_assignment_course_refs(qs)
        except Exception:
            refs = []

    try:
        if not isinstance(cached, dict):
            cached = {}
        cached[cache_key] = tuple(refs)
        setattr(user, cache_attr, cached)
    except Exception:
        pass
    return refs


def _preceptor_can_access_course(user, *, school=None, school_course=None, curso=None) -> bool:
    refs = _message_course_refs_for_user(user, school=school, role="preceptor")
    if not refs:
        return False
    try:
        return course_ref_matches(
            refs,
            school=school,
            school_course_id=getattr(school_course, "id", None),
            course_code=curso,
        )
    except Exception:
        return False


def _profesor_can_access_course(user, *, school=None, school_course=None, curso=None) -> bool:
    refs = _message_course_refs_for_user(user, school=school, role="profesor")
    if not refs:
        return False
    try:
        return course_ref_matches(
            refs,
            school=school,
            school_course_id=getattr(school_course, "id", None),
            course_code=curso,
        )
    except Exception:
        return False


def _authorize_staff_for_course(user, *, school=None, school_course=None, curso=None) -> bool:
    if _staff_can_send_schoolwide(user):
        return True

    groups = get_user_group_names_lower(user)
    if not groups:
        return False
    joined = " ".join(groups)
    if "preceptor" in joined:
        return _preceptor_can_access_course(user, school=school, school_course=school_course, curso=curso)
    if ("profesor" in joined) or ("docente" in joined):
        return _profesor_can_access_course(user, school=school, school_course=school_course, curso=curso)
    return False


def _authorize_staff_for_alumno(user, alumno) -> bool:
    if alumno is None:
        return _staff_can_send_schoolwide(user)
    return _authorize_staff_for_course(
        user,
        school=getattr(alumno, "school", None),
        school_course=getattr(alumno, "school_course", None),
        curso=getattr(alumno, "curso", None),
    )


def _get_sender_obj(m):
    sf = _sender_field()
    return getattr(m, sf, None)


def _get_recipient_obj(m):
    rf = _recipient_field()
    return getattr(m, rf, None)


def _get_curso_value(m):
    school_course = getattr(m, "school_course", None)
    school_course_code = getattr(school_course, "code", None) if school_course is not None else None
    if school_course_code:
        return school_course_code
    return getattr(m, "curso", None)


def _get_school_course_id_value(m):
    return getattr(m, "school_course_id", None)


def _get_school_course_name_value(m):
    school_course = getattr(m, "school_course", None)
    school_course_name = getattr(school_course, "name", None) if school_course is not None else None
    school_course_code = getattr(school_course, "code", None) if school_course is not None else None
    return school_course_name or school_course_code or _get_curso_value(m)


def _serialize_msg(m):
    """Serialización consistente para front (mantiene emisor/receptor por compat)."""
    flags = _flags()
    sender_obj = _get_sender_obj(m)
    recipient_obj = _get_recipient_obj(m)
    alumno_obj = getattr(m, "alumno", None) if flags["has_alumno"] else None

    item = {
        "id": m.id,
        "asunto": getattr(m, "asunto", "") or "",
        "contenido": getattr(m, "contenido", "") or "",
        "fecha_envio": getattr(m, "fecha_envio", None),
        "fecha": getattr(m, "fecha_envio", None),
        "school_course_id": _get_school_course_id_value(m),
        "school_course_name": _get_school_course_name_value(m),

        "emisor": _user_label(sender_obj),
        "receptor": _user_label(recipient_obj),
        "emisor_id": getattr(sender_obj, "id", None),
        "receptor_id": getattr(recipient_obj, "id", None),

        "remitente": _user_label(getattr(m, "remitente", None)) if flags["has_remitente"] else None,
        "destinatario": _user_label(getattr(m, "destinatario", None)) if flags["has_destinatario"] else None,
        "remitente_id": getattr(getattr(m, "remitente", None), "id", None) if flags["has_remitente"] else None,
        "destinatario_id": getattr(getattr(m, "destinatario", None), "id", None) if flags["has_destinatario"] else None,
    }
    if alumno_obj is not None:
        item["alumno_id"] = getattr(alumno_obj, "id", None)
        item["alumno_legajo"] = getattr(alumno_obj, "id_alumno", None)
        item["alumno_nombre"] = " ".join(
            part
            for part in [
                getattr(alumno_obj, "apellido", None),
                getattr(alumno_obj, "nombre", None),
            ]
            if part
        ).strip()
    elif flags["has_alumno"]:
        item["alumno_id"] = getattr(m, "alumno_id", None)

    if hasattr(m, "reply_to_id"):
        item["reply_to"] = m.reply_to_id
    if hasattr(m, "thread_id"):
        try:
            item["thread_id"] = str(m.thread_id)
        except Exception:
            item["thread_id"] = None

    if flags["has_leido"]:
        try:
            item["leido"] = bool(getattr(m, "leido"))
        except Exception:
            item["leido"] = None
    if flags["has_leido_en"]:
        item["leido_en"] = getattr(m, "leido_en", None)

    return item


def _mark_qs_as_read(qs):
    flags = _flags()
    has_leido = flags["has_leido"]
    has_leido_en = flags["has_leido_en"]

    if has_leido and has_leido_en:
        return qs.filter(models.Q(leido=False) | models.Q(leido_en__isnull=True)).update(
            leido=True, leido_en=timezone.now()
        )
    if has_leido:
        return qs.filter(leido=False).update(leido=True)
    if has_leido_en:
        return qs.filter(leido_en__isnull=True).update(leido_en=timezone.now())
    return 0


def _message_is_unread(msg) -> bool:
    flags = _flags()
    has_leido = flags["has_leido"]
    has_leido_en = flags["has_leido_en"]

    if has_leido and getattr(msg, "leido", None) is False:
        return True
    if has_leido_en and getattr(msg, "leido_en", None) is None:
        return True
    return False


def _user_is_alumno_or_padre(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return user_in_groups(user, "Alumnos", "Alumno", "Padres")


def _user_can_filter_inbox_by_alumno(user, alumno) -> bool:
    if not user or not getattr(user, "is_authenticated", False) or alumno is None:
        return False
    if getattr(user, "is_superuser", False):
        return True
    if getattr(alumno, "padre_id", None) == getattr(user, "id", None):
        return True
    if getattr(alumno, "usuario_id", None) == getattr(user, "id", None):
        return True
    return _authorize_staff_for_alumno(user, alumno)


def _can_include_legacy_course_messages_for_alumno(user, alumno) -> bool:
    if getattr(user, "is_superuser", False):
        return True

    school_course_id = getattr(alumno, "school_course_id", None)
    curso = str(getattr(alumno, "curso", "") or "").strip()
    if not school_course_id and not curso:
        return False

    siblings = Alumno.objects.filter(padre_id=getattr(user, "id", None))
    if school_course_id:
        siblings = siblings.filter(school_course_id=school_course_id)
    else:
        siblings = siblings.filter(curso__iexact=curso)

    try:
        return len(list(siblings.values_list("id", flat=True)[:2])) == 1
    except Exception:
        return False


def _filter_messages_for_alumno(qs, alumno, *, user=None):
    flags = _flags()
    if alumno is None or not flags["has_alumno"]:
        return qs

    q = models.Q(alumno=alumno)

    if _can_include_legacy_course_messages_for_alumno(user, alumno):
        school_course_id = getattr(alumno, "school_course_id", None)
        curso = str(getattr(alumno, "curso", "") or "").strip()
        if school_course_id:
            q |= models.Q(alumno__isnull=True, school_course_id=school_course_id)
        elif curso:
            q |= models.Q(alumno__isnull=True, curso__iexact=curso)

    return qs.filter(q)


def _coerce_json(request):
    if hasattr(request, "data") and request.data:
        return request.data
    try:
        raw = (request.body or b"").decode("utf-8")
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _get_user_by_id(uid):
    try:
        return User.objects.get(pk=int(uid), is_active=True)
    except Exception:
        return None


def _get_alumno_by_any_id(alumno_id, school=None):
    """Acepta PK numérica o legajo (id_alumno) si existe."""
    if alumno_id in (None, "", []):
        return None
    try:
        if str(alumno_id).isdigit():
            qs = scope_queryset_to_school(Alumno.objects.all(), school)
            return qs.get(pk=int(alumno_id))
        if _has_field(Alumno, "id_alumno"):
            # case-insensitive para evitar problemas de mayúsculas/minúsculas
            qs = scope_queryset_to_school(Alumno.objects.all(), school)
            return qs.get(id_alumno__iexact=str(alumno_id))
        return None
    except Alumno.DoesNotExist:
        return None


def _get_alumno_by_any_id_prefetched(alumno_id, school=None):
    if alumno_id in (None, "", []):
        return None
    qs = scope_queryset_to_school(
        Alumno.objects.select_related("school", "school_course", "usuario", "padre"),
        school,
    )
    try:
        if str(alumno_id).isdigit():
            return qs.get(pk=int(alumno_id))
        if _has_field(Alumno, "id_alumno"):
            return qs.get(id_alumno__iexact=str(alumno_id))
        return None
    except Alumno.DoesNotExist:
        return None


def _user_id_safe(user):
    """Devuelve el id del usuario si está autenticado; si no, None.
    Evita crashes cuando llega AnonymousUser/SimpleLazyObject.
    """
    try:
        if user is None:
            return None
        if hasattr(user, "is_authenticated") and not user.is_authenticated:
            return None
        uid = getattr(user, "id", None) or getattr(user, "pk", None)
        if uid is None:
            return None
        return int(uid)
    except Exception:
        return None


def _qs_inbox_for_user(user, school=None):
    rf = _recipient_field()
    uid = _user_id_safe(user)
    if not uid:
        return Mensaje.objects.none()
    # Usamos *_id para evitar que Django intente castear objetos raros a int.
    qs = Mensaje.objects.filter(**{f"{rf}_id": uid})
    return scope_queryset_to_school(qs, school)


def _infer_tipo_remitente(user):
    if user_has_group_fragment(user, "precep"):
        return "Preceptor"
    if user_has_group_fragment(user, "direct"):
        return "Directivo"
    if user_has_group_fragment(user, "profe"):
        return "Profesor"
    return "usuario"


def _unique_users(users):
    out = []
    seen = set()
    for u in users:
        uid = getattr(u, "id", None)
        if not u or uid in seen:
            continue
        seen.add(uid)
        out.append(u)
    return out


def _fallback_user_for_alumno(alumno):
    try:
        if alumno is None:
            return None
        if _has_field(Alumno, "id_alumno"):
            code = str(getattr(alumno, "id_alumno", "") or "").strip()
            if code:
                # case-insensitive para que funcione aunque el username esté en minúsculas
                return User.objects.filter(username__iexact=code, is_active=True).first()
    except Exception:
        pass
    return None


def _notif_url_for_msg(msg):
    try:
        if _threads_enabled() and getattr(msg, "thread_id", None):
            return f"/mensajes/hilo/{getattr(msg, 'thread_id')}"
        message_id = getattr(msg, "id", None)
        if message_id is not None:
            return f"/mensajes/hilo/{message_id}"
    except Exception:
        pass
    return "/mensajes"


def _notify_msg(*, msg, receptor, alumno=None, actor=None):
    """
    Crea notificación (campana) para mensajes.
    No debe bloquear el envío si falla.
    """
    try:
        asunto = (getattr(msg, "asunto", "") or "").strip()
        actor_label = _user_label(actor).strip() if actor is not None else ""
        if actor_label and asunto:
            titulo = f"{actor_label}: {asunto}"
        elif actor_label:
            titulo = f"Nuevo mensaje de {actor_label}"
        else:
            titulo = asunto or "Nuevo mensaje"
        contenido = (getattr(msg, "contenido", "") or "").strip()
        descripcion = (contenido[:160] + "…") if len(contenido) > 160 else contenido
        meta = {
            "mensaje_id": getattr(msg, "id", None),
            "thread_id": str(getattr(msg, "thread_id", "")) if _threads_enabled() else str(getattr(msg, "id", "")),
            "school_course_id": _get_school_course_id_value(msg),
            "school_course_name": _get_school_course_name_value(msg),
            "remitente_id": getattr(actor, "id", None),
        }
        if alumno is not None:
            meta["alumno_id"] = getattr(alumno, "id", None)
        school_ref = getattr(msg, "school", None) or getattr(alumno, "school", None)

        Notificacion.objects.create(
            school=school_ref,
            destinatario=receptor,
            tipo="mensaje",
            titulo=titulo,
            descripcion=descripcion or None,
            url=_notif_url_for_msg(msg),
            leida=False,
            meta=meta,
        )
        try:
            to_email = (getattr(receptor, "email", "") or "").strip()
            if to_email:
                send_message_email(
                    to_email=to_email,
                    subject=titulo or "Nuevo mensaje",
                    content=descripcion or contenido or "",
                    actor_label=actor_label,
                )
        except Exception:
            pass
    except Exception:
        pass


def _apply_conversation_window(qs, request):
    """
    Devuelve (qs_ventana, has_more, next_before_id)

    Estrategia:
    - Siempre trabajamos con ids (rápido).
    - Tomamos últimos N (orden descendente, slice) y luego reordenamos ascendente
      para mostrar "conversación" de viejo->nuevo.
    - Soporta before_id para ir más atrás.
    """
    limit = _parse_limit(request, DEFAULT_CONV_LIMIT)
    before_id = _parse_before_id(request)

    if before_id:
        qs = qs.filter(id__lt=before_id)

    # Traer N+1 para saber si hay más
    base = qs.order_by("-id")
    rows = list(base[: limit + 1])
    has_more = len(rows) > limit
    rows = rows[:limit]

    if not rows:
        return [], False, None

    # next_before_id = id mínimo del lote (para pedir más viejos)
    min_id = min(m.id for m in rows)
    next_before_id = min_id

    # Orden ascendente para UI
    rows.sort(key=lambda m: m.id)
    return rows, has_more, next_before_id


def _qs_conversacion_por_participantes(base_msg, school=None):
    sf = _sender_field()
    rf = _recipient_field()

    a = getattr(base_msg, sf, None)
    b = getattr(base_msg, rf, None)

    if not a or not b:
        return Mensaje.objects.none()

    q = Mensaje.objects.filter(
        models.Q(**{sf: a, rf: b}) | models.Q(**{sf: b, rf: a})
    )

    course_q = build_course_membership_q(
        school_course_id=_get_school_course_id_value(base_msg),
        course_code=_get_curso_value(base_msg),
        school_course_field="school_course",
        code_field="curso",
    )
    if course_q is not None:
        q = q.filter(course_q)

    if _flags()["has_alumno"]:
        base_alumno = getattr(base_msg, "alumno", None)
        if base_alumno is not None:
            q = q.filter(alumno=base_alumno)

    # IMPORTANTE: no ordenamos acá, lo hace _apply_conversation_window
    school_ref = school or getattr(base_msg, "school", None)
    return scope_queryset_to_school(q, school_ref)
