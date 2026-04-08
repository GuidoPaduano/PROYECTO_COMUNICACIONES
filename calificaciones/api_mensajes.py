# calificaciones/api_mensajes.py
from django.views.decorators.csrf import csrf_exempt

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

from django.core.exceptions import FieldDoesNotExist
from django.utils import timezone
from django.db import models
from django.contrib.auth import get_user_model

from .course_access import build_course_membership_q, course_ref_matches, get_assignment_course_refs
from .models import Alumno, Mensaje, Notificacion, resolve_school_course_for_value
from .resend_email import send_message_email
from .schools import get_request_school, scope_queryset_to_school
from .user_groups import get_user_group_names_lower, user_has_group_fragment, user_in_groups
from .utils_cursos import resolve_course_reference

from uuid import UUID, uuid4
import json
import re
from functools import lru_cache

User = get_user_model()

try:
    from .models_preceptores import PreceptorCurso, ProfesorCurso  # type: ignore
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


def _message_base_queryset(*, school=None):
    sf = _sender_field()
    rf = _recipient_field()
    qs = scope_queryset_to_school(Mensaje.objects.all(), school)
    return _safe_select_related(qs, sf, rf, "school_course")


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


# ===================== Envíos =====================
@csrf_exempt
@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def enviar_mensaje(request):
    flags = _flags()
    data = _coerce_json(request)
    active_school = get_request_school(request)

    asunto = (data.get("asunto") or "").strip()
    contenido = (data.get("contenido") or "").strip()
    tipo = (data.get("tipo") or "").strip().lower() or "mensaje"
    school_course_ref, curso, course_error = resolve_course_reference(
        school=active_school,
        raw_course=data.get("curso"),
        raw_school_course_id=data.get("school_course_id"),
        required=False,
    )

    alumno_id = data.get("alumno_id") or data.get("id_alumno")
    receptor_id = data.get("receptor_id")

    if not asunto or not contenido:
        return Response({"detail": "asunto y contenido son requeridos."}, status=400)
    if course_error:
        return Response({"detail": course_error}, status=400)

    alumno = _get_alumno_by_any_id_prefetched(alumno_id, school=active_school) if alumno_id not in (None, "", []) else None
    if alumno is not None and not _authorize_staff_for_alumno(request.user, alumno):
        return Response({"detail": "No autorizado para ese alumno."}, status=403)
    if alumno is None and not _staff_can_send_schoolwide(request.user):
        return Response({"detail": "No autorizado."}, status=403)

    sf = _sender_field()
    rf = _recipient_field()

    destinatarios = []

    if receptor_id not in (None, "", []):
        receptor = _get_user_by_id(receptor_id)
        if receptor is None:
            return Response({"detail": "receptor_id inválido."}, status=400)
        destinatarios = [receptor]
    else:
        if alumno is None:
            return Response({"detail": "Debe indicarse alumno_id/id_alumno o receptor_id."}, status=400)

        if tipo == "comunicado":
            candidatos = [getattr(alumno, "padre", None), getattr(alumno, "usuario", None)]
        else:
            alumno_user = getattr(alumno, "usuario", None)
            if alumno_user is None:
                fb = _fallback_user_for_alumno(alumno)
                candidatos = [fb, getattr(alumno, "padre", None)]
            else:
                candidatos = [alumno_user, getattr(alumno, "padre", None)]

        destinatarios = _unique_users(candidatos)

        if not destinatarios:
            fb = _fallback_user_for_alumno(alumno)
            if fb:
                destinatarios = [fb]

        if not destinatarios:
            return Response({"detail": "El alumno no tiene usuario/padre asignado (ni fallback por username)."}, status=400)

    ids = []
    first = None

    if alumno is not None:
        school_course_ref = getattr(alumno, "school_course", None) or school_course_ref
    elif curso and active_school is not None and school_course_ref is None:
        return Response({"detail": "No existe ese curso en el colegio activo."}, status=400)

    course_code = _course_code_for_storage(
        school_course=school_course_ref,
        curso=curso,
        alumno=alumno,
    )

    for receptor in destinatarios:
        kwargs = {
            sf: request.user,
            rf: receptor,
            "asunto": asunto,
            "contenido": contenido,
        }

        if course_code:
            kwargs["curso"] = course_code

        if flags["has_tipo"]:
            kwargs["tipo"] = tipo

        if flags["has_tipo_remitente"]:
            kwargs["tipo_remitente"] = _infer_tipo_remitente(request.user)

        if alumno is not None and flags["has_alumno"]:
            kwargs["alumno"] = alumno

        if flags["has_fecha_envio"]:
            kwargs["fecha_envio"] = timezone.now()
        if _has_field(Mensaje, "school"):
            kwargs["school"] = getattr(alumno, "school", None) or active_school
        if _has_field(Mensaje, "school_course") and school_course_ref is not None:
            kwargs["school_course"] = school_course_ref

        msg = Mensaje.objects.create(**kwargs)
        _notify_msg(msg=msg, receptor=receptor, alumno=alumno, actor=request.user)
        if first is None:
            first = msg
        ids.append(msg.id)

    return Response(
        {
            "id": first.id if first else None,
            "ids": ids,
            "mensajes_creados": len(ids),
            "thread_id": str(getattr(first, "thread_id")) if (first and _threads_enabled()) else str(first.id if first else ""),
            "receptor": getattr(destinatarios[0], "id", None) if destinatarios else None,
            "receptores": [getattr(u, "id", None) for u in destinatarios],
        },
        status=201,
    )


@csrf_exempt
@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def enviar_mensaje_grupal(request):
    flags = _flags()
    data = _coerce_json(request)
    active_school = get_request_school(request)
    school_course_ref, curso, course_error = resolve_course_reference(
        school=active_school,
        raw_course=data.get("curso"),
        raw_school_course_id=data.get("school_course_id"),
        required=True,
    )
    asunto = (data.get("asunto") or "").strip()
    contenido = (data.get("contenido") or "").strip()
    tipo = (data.get("tipo") or "").strip().lower() or "mensaje"

    if not asunto or not contenido:
        return Response({"detail": "asunto y contenido son requeridos."}, status=400)
    if course_error:
        return Response({"detail": course_error}, status=400)
    if active_school is not None and school_course_ref is None:
        return Response({"detail": "No existe ese curso en el colegio activo."}, status=400)
    course_code = _course_code_for_storage(school_course=school_course_ref, curso=curso)
    if not course_code:
        return Response({"detail": "school_course_id o curso, asunto y contenido son requeridos."}, status=400)
    if not _authorize_staff_for_course(
        request.user,
        school=active_school,
        school_course=school_course_ref,
        curso=course_code,
    ):
        return Response({"detail": "No autorizado para ese curso."}, status=403)

    alumnos = list(
        _alumnos_por_curso_qs(
            curso=course_code,
            school=active_school,
            school_course=school_course_ref,
        )
        .select_related("padre", "usuario", "school", "school_course")
        .order_by("id")
    )
    if not alumnos:
        return Response({"detail": "No hay alumnos para ese curso."}, status=404)

    fallback_users_by_legajo = {}
    legajos = sorted(
        {
            str(getattr(a, "id_alumno", "") or "").strip()
            for a in alumnos
            if getattr(a, "usuario_id", None) is None and str(getattr(a, "id_alumno", "") or "").strip()
        }
    )
    if legajos:
        try:
            fallback_users_by_legajo = {
                str(getattr(u, "username", "") or "").strip(): u
                for u in User.objects.filter(username__in=legajos, is_active=True)
            }
        except Exception:
            fallback_users_by_legajo = {}

    sf = _sender_field()
    rf = _recipient_field()

    alumnos_ok = 0
    mensajes_creados = 0
    sin_receptor = 0
    notifs = []

    for a in alumnos:
        if tipo == "comunicado":
            candidatos = [getattr(a, "padre", None), getattr(a, "usuario", None)]
        else:
            alumno_user = getattr(a, "usuario", None)
            if alumno_user is None:
                fb = fallback_users_by_legajo.get(str(getattr(a, "id_alumno", "") or "").strip())
                candidatos = [fb, getattr(a, "padre", None)]
            else:
                candidatos = [alumno_user, getattr(a, "padre", None)]

        destinatarios = _unique_users(candidatos)

        if not destinatarios:
            fb = fallback_users_by_legajo.get(str(getattr(a, "id_alumno", "") or "").strip())
            if fb:
                destinatarios = [fb]

        if not destinatarios:
            sin_receptor += 1
            continue

        alumnos_ok += 1

        for receptor in destinatarios:
            kwargs = {
                sf: request.user,
                rf: receptor,
                "asunto": asunto,
                "contenido": contenido,
            }

            alumno_course_code = _course_code_for_storage(
                school_course=getattr(a, "school_course", None) or school_course_ref,
                curso=course_code,
                alumno=a,
            )
            if alumno_course_code:
                kwargs["curso"] = alumno_course_code

            if flags["has_tipo"]:
                kwargs["tipo"] = tipo

            if flags["has_tipo_remitente"]:
                kwargs["tipo_remitente"] = _infer_tipo_remitente(request.user)

            if flags["has_alumno"]:
                kwargs["alumno"] = a

            if flags["has_fecha_envio"]:
                kwargs["fecha_envio"] = timezone.now()
            if _has_field(Mensaje, "school"):
                kwargs["school"] = getattr(a, "school", None) or active_school
            if _has_field(Mensaje, "school_course"):
                kwargs["school_course"] = getattr(a, "school_course", None) or school_course_ref

            msg = Mensaje.objects.create(**kwargs)
            mensajes_creados += 1
            try:
                to_email = (getattr(receptor, "email", "") or "").strip()
                if to_email:
                    actor_label = _user_label(request.user).strip()
                    send_message_email(
                        to_email=to_email,
                        subject=(getattr(msg, "asunto", "") or "Nuevo mensaje").strip(),
                        content=(getattr(msg, "contenido", "") or "").strip(),
                        actor_label=actor_label,
                    )
            except Exception:
                pass
            try:
                titulo = (getattr(msg, "asunto", "") or "").strip() or "Nuevo mensaje"
                contenido = (getattr(msg, "contenido", "") or "").strip()
                descripcion = (contenido[:160] + "…") if len(contenido) > 160 else contenido
                meta = {
                    "mensaje_id": getattr(msg, "id", None),
                    "thread_id": str(getattr(msg, "thread_id", "")) if _threads_enabled() else str(getattr(msg, "id", "")),
                    "school_course_id": _get_school_course_id_value(msg),
                    "school_course_name": _get_school_course_name_value(msg),
                    "remitente_id": getattr(request.user, "id", None),
                    "alumno_id": getattr(a, "id", None),
                }
                notifs.append(
                    Notificacion(
                        school=getattr(a, "school", None) or active_school,
                        destinatario=receptor,
                        tipo="mensaje",
                        titulo=titulo,
                        descripcion=descripcion or None,
                        url=_notif_url_for_msg(msg),
                        leida=False,
                        meta=meta,
                    )
                )
            except Exception:
                pass

    if notifs:
        try:
            Notificacion.objects.bulk_create(notifs, batch_size=500)
        except Exception:
            pass

    return Response(
        {
            "creados": alumnos_ok,
            "mensajes_creados": mensajes_creados,
            "sin_receptor": sin_receptor,
        },
        status=201,
    )


# ===================== Lectura / estado =====================
@csrf_exempt
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mensajes_unread_count(request):
    active_school = get_request_school(request)
    qs = _qs_inbox_for_user(request.user, school=active_school)

    flags = _flags()
    has_leido = flags["has_leido"]
    has_leido_en = flags["has_leido_en"]

    if has_leido and has_leido_en:
        return Response(
            {"count": qs.filter(models.Q(leido=False) | models.Q(leido_en__isnull=True)).count()},
            status=200,
        )

    if has_leido:
        return Response({"count": qs.filter(leido=False).count()}, status=200)

    if has_leido_en:
        return Response({"count": qs.filter(leido_en__isnull=True).count()}, status=200)

    return Response({"count": min(qs.count(), 50)}, status=200)


@csrf_exempt
@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mensajes_marcar_todos_leidos(request):
    active_school = get_request_school(request)
    qs = _qs_inbox_for_user(request.user, school=active_school)
    updated = _mark_qs_as_read(qs)
    if updated > 0:
        return Response({"actualizados": updated}, status=200)
    return Response(status=204)


@csrf_exempt
@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mensajes_marcar_leido(request, mensaje_id: int):
    active_school = get_request_school(request)
    try:
        m = _message_base_queryset(school=active_school).get(id=mensaje_id)
    except Mensaje.DoesNotExist:
        return Response({"detail": "Mensaje no encontrado."}, status=404)

    rf = _recipient_field()
    if getattr(m, rf, None) != request.user:
        return Response({"detail": "No autorizado."}, status=403)

    flags = _flags()
    has_leido = flags["has_leido"]
    has_leido_en = flags["has_leido_en"]

    changed = False
    if has_leido and getattr(m, "leido", None) is not True:
        m.leido = True
        changed = True
    if has_leido_en and getattr(m, "leido_en", None) is None:
        m.leido_en = timezone.now()
        changed = True

    if changed:
        update_fields = []
        if has_leido:
            update_fields.append("leido")
        if has_leido_en:
            update_fields.append("leido_en")
        m.save(update_fields=update_fields)

    return Response(status=204)




# ===================== Eliminar (bandeja) =====================
@csrf_exempt
@api_view(["DELETE", "POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mensajes_eliminar(request, mensaje_id: int):
    """
    DELETE /api/mensajes/<id>/eliminar/   (también acepta POST por compat)

    Elimina un mensaje de la bandeja del destinatario.
    """
    active_school = get_request_school(request)
    try:
        msg = _message_base_queryset(school=active_school).get(pk=mensaje_id)
    except Mensaje.DoesNotExist:
        return Response({"detail": "Mensaje no encontrado."}, status=404)

    rf = _recipient_field()
    destinatario = getattr(msg, rf, None)

    # Solo el destinatario (o superuser) puede eliminar de esa bandeja.
    if (destinatario is None) or (
        destinatario != request.user
        and not getattr(request.user, "is_superuser", False)
    ):
        return Response({"detail": "No autorizado."}, status=403)

    msg.delete()
    return Response({"id": mensaje_id}, status=200)
# ===================== Listados =====================
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mensajes_recibidos(request):
    active_school = get_request_school(request)
    qs = _qs_inbox_for_user(request.user, school=active_school)
    flags = _flags()

    if request.GET.get("solo_no_leidos") in ("1", "true", "True"):
        has_leido = flags["has_leido"]
        has_leido_en = flags["has_leido_en"]
        if has_leido and has_leido_en:
            qs = qs.filter(models.Q(leido=False) | models.Q(leido_en__isnull=True))
        elif has_leido:
            qs = qs.filter(leido=False)
        elif has_leido_en:
            qs = qs.filter(leido_en__isnull=True)

    if flags["has_fecha_envio"]:
        qs = qs.order_by("-fecha_envio", "-id")
    else:
        qs = qs.order_by("-id")

    limit = request.GET.get("limit")
    if limit:
        try:
            limit_i = max(1, min(int(limit), 500))
            qs = qs[:limit_i]
        except ValueError:
            pass

    sf = _sender_field()
    rf = _recipient_field()
    qs = _safe_select_related(qs, sf, rf, "school_course")

    data = [_serialize_msg(m) for m in qs]
    return Response(data, status=200)


mensajes_listar = mensajes_recibidos


# ===================== Conversaciones (hilos) =====================
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mensajes_conversacion_por_mensaje(request, mensaje_id: int):
    """
    GET /api/mensajes/conversacion/<mensaje_id>/?autoleer=1&limit=50&before_id=1234

    ✅ Optimizado:
    - Por defecto devuelve últimos 50 (rápido).
    - before_id permite traer más hacia atrás.
    - select_related para evitar N+1.
    """
    active_school = get_request_school(request)
    try:
        base = _message_base_queryset(school=active_school).get(id=mensaje_id)
    except Mensaje.DoesNotExist:
        return Response({"detail": "Mensaje no encontrado."}, status=404)

    user = request.user
    sf = _sender_field()
    rf = _recipient_field()

    if getattr(base, sf, None) != user and getattr(base, rf, None) != user:
        return Response({"detail": "No autorizado."}, status=403)

    # Caso 1: threads reales
    if _threads_enabled():
        if not getattr(base, "thread_id", None):
            base.thread_id = uuid4()
            base.save(update_fields=["thread_id"])

        qs = scope_queryset_to_school(Mensaje.objects.filter(thread_id=base.thread_id), active_school)
        qs = _safe_select_related(qs, sf, rf, "school_course")

        # Ventana (últimos N)
        rows, has_more, next_before_id = _apply_conversation_window(qs, request)

        # Autoleer solo lo visible (más rápido)
        if request.GET.get("autoleer") in ("1", "true", "True"):
            ids = [m.id for m in rows]
            if ids:
                _mark_qs_as_read(
                    scope_queryset_to_school(
                        Mensaje.objects.filter(id__in=ids, **{rf: user}),
                        active_school,
                    )
                )

        data = [_serialize_msg(m) for m in rows]
        return Response(
            {
                "thread_id": str(base.thread_id),
                "mensajes": data,
                "has_more": has_more,
                "next_before_id": next_before_id,
                "limit": _parse_limit(request),
            },
            status=200,
        )

    # Caso 2: SIN threads -> hilo virtual por participantes
    qs = _qs_conversacion_por_participantes(base, school=active_school)
    qs = _safe_select_related(qs, sf, rf, "school_course")

    rows, has_more, next_before_id = _apply_conversation_window(qs, request)

    if request.GET.get("autoleer") in ("1", "true", "True"):
        ids = [m.id for m in rows]
        if ids:
            _mark_qs_as_read(
                scope_queryset_to_school(
                    Mensaje.objects.filter(id__in=ids, **{rf: user}),
                    active_school,
                )
            )

    data = [_serialize_msg(m) for m in rows]
    return Response(
        {
            "thread_id": str(base.id),  # hilo virtual estable para el front
            "mensajes": data,
            "has_more": has_more,
            "next_before_id": next_before_id,
            "limit": _parse_limit(request),
        },
        status=200,
    )


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mensajes_conversacion_por_thread(request, thread_id: str):
    if not _threads_enabled():
        return Response({"detail": "Tu modelo Mensaje no soporta thread_id."}, status=400)

    active_school = get_request_school(request)
    try:
        tid = UUID(str(thread_id))
    except Exception:
        return Response({"detail": "thread_id inválido."}, status=400)

    user = request.user
    sf = _sender_field()
    rf = _recipient_field()

    thread_qs = scope_queryset_to_school(Mensaje.objects.filter(thread_id=tid), active_school)
    if not thread_qs.filter(
        models.Q(**{sf: user}) | models.Q(**{rf: user})
    ).exists():
        return Response({"detail": "No autorizado o hilo inexistente."}, status=404)

    qs = thread_qs
    qs = _safe_select_related(qs, sf, rf, "school_course")

    rows, has_more, next_before_id = _apply_conversation_window(qs, request)

    if request.GET.get("autoleer") in ("1", "true", "True"):
        ids = [m.id for m in rows]
        if ids:
            _mark_qs_as_read(
                scope_queryset_to_school(
                    Mensaje.objects.filter(id__in=ids, **{rf: user}),
                    active_school,
                )
            )

    data = [_serialize_msg(m) for m in rows]
    return Response(
        {
            "thread_id": str(tid),
            "mensajes": data,
            "has_more": has_more,
            "next_before_id": next_before_id,
            "limit": _parse_limit(request),
        },
        status=200,
    )


@csrf_exempt
@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mensajes_marcar_thread_leidos(request, thread_id: str):
    if not _threads_enabled():
        return Response({"detail": "Tu modelo Mensaje no soporta thread_id."}, status=400)

    active_school = get_request_school(request)
    try:
        tid = UUID(str(thread_id))
    except Exception:
        return Response({"detail": "thread_id inválido."}, status=400)

    user = request.user
    sf = _sender_field()
    rf = _recipient_field()

    thread_qs = scope_queryset_to_school(Mensaje.objects.filter(thread_id=tid), active_school)
    if not thread_qs.filter(
        models.Q(**{sf: user}) | models.Q(**{rf: user})
    ).exists():
        return Response({"detail": "No autorizado o hilo inexistente."}, status=404)

    updated = _mark_qs_as_read(
        scope_queryset_to_school(
            Mensaje.objects.filter(thread_id=tid, **{rf: user}),
            active_school,
        )
    )
    return Response({"actualizados": updated}, status=200)


# ===================== Responder =====================
@csrf_exempt
@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def responder_mensaje(request):
    active_school = get_request_school(request)
    flags = _flags()
    try:
        data = request.data if hasattr(request, "data") else json.loads(request.body.decode("utf-8"))
    except Exception:
        data = {}

    mensaje_id = data.get("mensaje_id") or data.get("id") or data.get("mensajeId")
    asunto = (data.get("asunto") or "").strip()
    contenido = (data.get("contenido") or "").strip()

    if not mensaje_id or not contenido:
        return Response({"detail": "mensaje_id y contenido son requeridos."}, status=400)

    try:
        original = scope_queryset_to_school(Mensaje.objects.all(), active_school).get(id=mensaje_id)
    except Mensaje.DoesNotExist:
        return Response({"detail": "Mensaje no encontrado."}, status=404)

    sf = _sender_field()
    rf = _recipient_field()

    if getattr(original, rf, None) != request.user:
        return Response({"detail": "No podés responder un mensaje que no recibiste."}, status=403)

    # Normalizar asunto para evitar "Re: Re: Re:"
    asunto_normalizado = _normalize_subject(asunto) if asunto else _normalize_subject(getattr(original, "asunto", ""))
    if asunto_normalizado:
        asunto = f"Re: {asunto_normalizado}"
    else:
        asunto = "Re:"

    original_sender = getattr(original, sf, None)
    if not original_sender:
        return Response({"detail": "No se pudo resolver el remitente del mensaje original."}, status=400)

    nuevo_kwargs = {
        sf: request.user,
        rf: original_sender,
        "asunto": asunto,
        "contenido": contenido,
    }

    original_course_code = _get_curso_value(original)
    if original_course_code:
        nuevo_kwargs["curso"] = original_course_code

    if flags["has_reply_to"]:
        nuevo_kwargs["reply_to"] = original

    if _threads_enabled():
        if not getattr(original, "thread_id", None):
            original.thread_id = uuid4()
            original.save(update_fields=["thread_id"])
        nuevo_kwargs["thread_id"] = getattr(original, "thread_id", None)

    if flags["has_tipo_remitente"]:
        nuevo_kwargs["tipo_remitente"] = _infer_tipo_remitente(request.user)

    if flags["has_fecha_envio"]:
        nuevo_kwargs["fecha_envio"] = timezone.now()

    alumno_ref = getattr(original, "alumno", None) if flags["has_alumno"] else None
    if alumno_ref is not None and flags["has_alumno"]:
        nuevo_kwargs["alumno"] = alumno_ref

    if _has_field(Mensaje, "school"):
        nuevo_kwargs["school"] = (
            getattr(original, "school", None)
            or getattr(alumno_ref, "school", None)
            or active_school
        )
    if _has_field(Mensaje, "school_course"):
        school_course_ref = (
            getattr(original, "school_course", None)
            or getattr(alumno_ref, "school_course", None)
        )
        if school_course_ref is not None:
            nuevo_kwargs["school_course"] = school_course_ref

    nuevo = Mensaje.objects.create(**nuevo_kwargs)
    try:
        _notify_msg(msg=nuevo, receptor=original_sender, alumno=alumno_ref, actor=request.user)
    except Exception:
        pass

    has_leido = flags["has_leido"]
    has_leido_en = flags["has_leido_en"]
    update_fields = []

    if has_leido and getattr(original, "leido", None) is not True:
        original.leido = True
        update_fields.append("leido")

    if has_leido_en and getattr(original, "leido_en", None) is None:
        original.leido_en = timezone.now()
        update_fields.append("leido_en")

    if update_fields:
        original.save(update_fields=update_fields)

    return Response(
        {
            "id": nuevo.id,
            "thread_id": str(getattr(nuevo, "thread_id")) if _threads_enabled() else str(original.id),
        },
        status=201,
    )


mensajes_responder = responder_mensaje


# ===================== Mantenimiento / Normalización (opcional) =====================
@csrf_exempt
@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mensajes_normalizar_flags(request):
    active_school = get_request_school(request)
    body = {}
    try:
        body = request.data if hasattr(request, "data") else json.loads(request.body.decode("utf-8"))
    except Exception:
        body = {}

    scope_all = False
    if body.get("scope") == "all":
        if not request.user.is_superuser:
            return Response({"detail": "Solo superusuarios pueden usar scope=all."}, status=403)
        scope_all = True

    flags = _flags()
    has_leido = flags["has_leido"]
    has_leido_en = flags["has_leido_en"]

    if not (has_leido and has_leido_en):
        return Response({"actualizados": 0, "scope": "self" if not scope_all else "all"}, status=200)

    if scope_all:
        base_qs = scope_queryset_to_school(Mensaje.objects.all(), active_school)
    else:
        base_qs = _qs_inbox_for_user(request.user, school=active_school)
    updated = base_qs.filter(leido=True, leido_en__isnull=True).update(leido_en=timezone.now())
    return Response({"actualizados": updated, "scope": "all" if scope_all else "self"}, status=200)
