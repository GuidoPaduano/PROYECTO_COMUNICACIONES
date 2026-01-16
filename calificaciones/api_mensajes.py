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
from rest_framework_simplejwt.authentication import JWTAuthentication

from django.core.exceptions import FieldDoesNotExist
from django.utils import timezone
from django.db import models
from django.contrib.auth import get_user_model

from .models import Alumno, Mensaje

from uuid import UUID, uuid4
import json

User = get_user_model()

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


def _sender_field() -> str:
    """Compat: Mensaje.remitente (nuevo) vs Mensaje.emisor (viejo)."""
    return "remitente" if _has_field(Mensaje, "remitente") else "emisor"


def _recipient_field() -> str:
    """Compat: Mensaje.destinatario (nuevo) vs Mensaje.receptor (viejo)."""
    return "destinatario" if _has_field(Mensaje, "destinatario") else "receptor"


def _curso_field() -> str:
    """Compat: Mensaje.curso_asociado (viejo) vs Mensaje.curso (nuevo)."""
    if _has_field(Mensaje, "curso_asociado"):
        return "curso_asociado"
    if _has_field(Mensaje, "curso"):
        return "curso"
    return ""


def _threads_enabled() -> bool:
    """True si el modelo Mensaje tiene thread_id."""
    return _has_field(Mensaje, "thread_id")


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


def _user_label(u):
    try:
        return (u.get_full_name() or u.username) if u else ""
    except Exception:
        return getattr(u, "username", "") or ""


def _get_sender_obj(m):
    sf = _sender_field()
    return getattr(m, sf, None)


def _get_recipient_obj(m):
    rf = _recipient_field()
    return getattr(m, rf, None)


def _get_curso_value(m):
    cf = _curso_field()
    return getattr(m, cf, None) if cf else None


def _serialize_msg(m):
    """Serialización consistente para front (mantiene emisor/receptor por compat)."""
    sender_obj = _get_sender_obj(m)
    recipient_obj = _get_recipient_obj(m)

    item = {
        "id": m.id,
        "asunto": getattr(m, "asunto", "") or "",
        "contenido": getattr(m, "contenido", "") or "",
        "fecha_envio": getattr(m, "fecha_envio", None),
        "fecha": getattr(m, "fecha_envio", None),

        "curso": _get_curso_value(m),
        "curso_asociado": (
            getattr(m, "curso_asociado", None)
            if _has_field(Mensaje, "curso_asociado")
            else _get_curso_value(m)
        ),

        "emisor": _user_label(sender_obj),
        "receptor": _user_label(recipient_obj),
        "emisor_id": getattr(sender_obj, "id", None),
        "receptor_id": getattr(recipient_obj, "id", None),

        "remitente": _user_label(getattr(m, "remitente", None)) if _has_field(Mensaje, "remitente") else None,
        "destinatario": _user_label(getattr(m, "destinatario", None)) if _has_field(Mensaje, "destinatario") else None,
        "remitente_id": getattr(getattr(m, "remitente", None), "id", None) if _has_field(Mensaje, "remitente") else None,
        "destinatario_id": getattr(getattr(m, "destinatario", None), "id", None) if _has_field(Mensaje, "destinatario") else None,
    }

    if hasattr(m, "reply_to_id"):
        item["reply_to"] = m.reply_to_id
    if hasattr(m, "thread_id"):
        try:
            item["thread_id"] = str(m.thread_id)
        except Exception:
            item["thread_id"] = None

    if _has_field(Mensaje, "leido"):
        try:
            item["leido"] = bool(getattr(m, "leido"))
        except Exception:
            item["leido"] = None
    if _has_field(Mensaje, "leido_en"):
        item["leido_en"] = getattr(m, "leido_en", None)

    return item


def _mark_qs_as_read(qs):
    has_leido = _has_field(Mensaje, "leido")
    has_leido_en = _has_field(Mensaje, "leido_en")

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


def _get_alumno_by_any_id(alumno_id):
    """Acepta PK numérica o legajo (id_alumno) si existe."""
    if alumno_id in (None, "", []):
        return None
    try:
        if str(alumno_id).isdigit():
            return Alumno.objects.get(pk=int(alumno_id))
        if _has_field(Alumno, "id_alumno"):
            # case-insensitive para evitar problemas de mayúsculas/minúsculas
            return Alumno.objects.get(id_alumno__iexact=str(alumno_id))
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


def _qs_inbox_for_user(user):
    rf = _recipient_field()
    uid = _user_id_safe(user)
    if not uid:
        return Mensaje.objects.none()
    # Usamos *_id para evitar que Django intente castear objetos raros a int.
    return Mensaje.objects.filter(**{f"{rf}_id": uid})


def _qs_sent_for_user(user):
    sf = _sender_field()
    uid = _user_id_safe(user)
    if not uid:
        return Mensaje.objects.none()
    return Mensaje.objects.filter(**{f"{sf}_id": uid})



def _infer_tipo_remitente(user):
    try:
        if user.groups.filter(name__icontains="precep").exists():
            return "Preceptor"
        if user.groups.filter(name__icontains="direct").exists():
            return "Directivo"
        if user.groups.filter(name__icontains="profe").exists():
            return "Profesor"
    except Exception:
        pass
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


def _qs_conversacion_por_participantes(base_msg):
    sf = _sender_field()
    rf = _recipient_field()

    a = getattr(base_msg, sf, None)
    b = getattr(base_msg, rf, None)

    if not a or not b:
        return Mensaje.objects.none()

    q = Mensaje.objects.filter(
        models.Q(**{sf: a, rf: b}) | models.Q(**{sf: b, rf: a})
    )

    cf = _curso_field()
    if cf:
        base_curso = getattr(base_msg, cf, None)
        if base_curso not in (None, "", []):
            q = q.filter(**{cf: base_curso})

    if _has_field(Mensaje, "alumno"):
        base_alumno = getattr(base_msg, "alumno", None)
        if base_alumno is not None:
            q = q.filter(alumno=base_alumno)

    # IMPORTANTE: no ordenamos acá, lo hace _apply_conversation_window
    return q


# ===================== Envíos =====================
@csrf_exempt
@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def enviar_mensaje(request):
    data = _coerce_json(request)

    asunto = (data.get("asunto") or "").strip()
    contenido = (data.get("contenido") or "").strip()
    tipo = (data.get("tipo") or "").strip().lower() or "mensaje"
    curso = (data.get("curso") or "").strip()

    alumno_id = data.get("alumno_id") or data.get("id_alumno")
    receptor_id = data.get("receptor_id")

    if not asunto or not contenido:
        return Response({"detail": "asunto y contenido son requeridos."}, status=400)

    alumno = _get_alumno_by_any_id(alumno_id) if alumno_id not in (None, "", []) else None

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
            candidatos = [getattr(alumno, "usuario", None), getattr(alumno, "padre", None)]

        destinatarios = _unique_users(candidatos)

        if not destinatarios:
            fb = _fallback_user_for_alumno(alumno)
            if fb:
                destinatarios = [fb]

        if not destinatarios:
            return Response({"detail": "El alumno no tiene usuario/padre asignado (ni fallback por username)."}, status=400)

    cf = _curso_field()

    ids = []
    first = None

    for receptor in destinatarios:
        kwargs = {
            sf: request.user,
            rf: receptor,
            "asunto": asunto,
            "contenido": contenido,
        }

        if cf:
            if curso:
                kwargs[cf] = curso
            elif alumno is not None and getattr(alumno, "curso", None):
                kwargs[cf] = getattr(alumno, "curso", None)

        if _has_field(Mensaje, "tipo"):
            kwargs["tipo"] = tipo

        if _has_field(Mensaje, "tipo_remitente"):
            kwargs["tipo_remitente"] = _infer_tipo_remitente(request.user)

        if alumno is not None and _has_field(Mensaje, "alumno"):
            kwargs["alumno"] = alumno

        if _has_field(Mensaje, "fecha_envio"):
            kwargs["fecha_envio"] = timezone.now()

        msg = Mensaje.objects.create(**kwargs)
        if first is None:
            first = msg
        ids.append(msg.id)

    return Response(
        {
            "ok": True,
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
    data = _coerce_json(request)
    curso = (data.get("curso") or "").strip()
    asunto = (data.get("asunto") or "").strip()
    contenido = (data.get("contenido") or "").strip()
    tipo = (data.get("tipo") or "").strip().lower() or "mensaje"

    if not curso or not asunto or not contenido:
        return Response({"detail": "curso, asunto y contenido son requeridos."}, status=400)

    alumnos = list(Alumno.objects.filter(curso=curso).order_by("id"))
    if not alumnos:
        return Response({"detail": "No hay alumnos para ese curso."}, status=404)

    sf = _sender_field()
    rf = _recipient_field()
    cf = _curso_field()

    alumnos_ok = 0
    mensajes_creados = 0
    sin_receptor = 0

    for a in alumnos:
        if tipo == "comunicado":
            candidatos = [getattr(a, "padre", None), getattr(a, "usuario", None)]
        else:
            candidatos = [getattr(a, "usuario", None), getattr(a, "padre", None)]

        destinatarios = _unique_users(candidatos)

        if not destinatarios:
            fb = _fallback_user_for_alumno(a)
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

            if cf:
                kwargs[cf] = curso

            if _has_field(Mensaje, "tipo"):
                kwargs["tipo"] = tipo

            if _has_field(Mensaje, "tipo_remitente"):
                kwargs["tipo_remitente"] = _infer_tipo_remitente(request.user)

            if _has_field(Mensaje, "alumno"):
                kwargs["alumno"] = a

            if _has_field(Mensaje, "fecha_envio"):
                kwargs["fecha_envio"] = timezone.now()

            Mensaje.objects.create(**kwargs)
            mensajes_creados += 1

    return Response(
        {
            "ok": True,
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
    qs = _qs_inbox_for_user(request.user)

    has_leido = _has_field(Mensaje, "leido")
    has_leido_en = _has_field(Mensaje, "leido_en")

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
    qs = _qs_inbox_for_user(request.user)
    updated = _mark_qs_as_read(qs)
    if updated > 0:
        return Response({"ok": True, "actualizados": updated}, status=200)
    return Response(status=204)


@csrf_exempt
@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mensajes_marcar_leido(request, mensaje_id: int):
    try:
        m = Mensaje.objects.get(id=mensaje_id)
    except Mensaje.DoesNotExist:
        return Response({"detail": "Mensaje no encontrado."}, status=404)

    rf = _recipient_field()
    if getattr(m, rf, None) != request.user:
        return Response({"detail": "No autorizado."}, status=403)

    has_leido = _has_field(Mensaje, "leido")
    has_leido_en = _has_field(Mensaje, "leido_en")

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

    return Response({"ok": True}, status=200)




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
    try:
        msg = Mensaje.objects.get(pk=mensaje_id)
    except Mensaje.DoesNotExist:
        return Response({"detail": "Mensaje no encontrado."}, status=404)

    rf = _recipient_field()
    destinatario = getattr(msg, rf, None)

    # Solo el destinatario (o staff/superuser) puede eliminar
    if (destinatario is None) or (
        destinatario != request.user
        and not getattr(request.user, "is_staff", False)
        and not getattr(request.user, "is_superuser", False)
    ):
        return Response({"detail": "No autorizado."}, status=403)

    msg.delete()
    return Response({"ok": True, "id": mensaje_id}, status=200)
# ===================== Listados =====================
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mensajes_recibidos(request):
    qs = _qs_inbox_for_user(request.user)

    if request.GET.get("solo_no_leidos") in ("1", "true", "True"):
        has_leido = _has_field(Mensaje, "leido")
        has_leido_en = _has_field(Mensaje, "leido_en")
        if has_leido and has_leido_en:
            qs = qs.filter(models.Q(leido=False) | models.Q(leido_en__isnull=True))
        elif has_leido:
            qs = qs.filter(leido=False)
        elif has_leido_en:
            qs = qs.filter(leido_en__isnull=True)

    if _has_field(Mensaje, "fecha_envio"):
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
    qs = _safe_select_related(qs, sf, rf)

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
    try:
        base = Mensaje.objects.get(id=mensaje_id)
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

        if not Mensaje.objects.filter(thread_id=base.thread_id).filter(
            models.Q(**{sf: user}) | models.Q(**{rf: user})
        ).exists():
            return Response({"detail": "No autorizado."}, status=403)

        qs = Mensaje.objects.filter(thread_id=base.thread_id)
        qs = _safe_select_related(qs, sf, rf)

        # Ventana (últimos N)
        rows, has_more, next_before_id = _apply_conversation_window(qs, request)

        # Autoleer solo lo visible (más rápido)
        if request.GET.get("autoleer") in ("1", "true", "True"):
            ids = [m.id for m in rows]
            if ids:
                _mark_qs_as_read(Mensaje.objects.filter(id__in=ids, **{rf: user}))

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
    qs = _qs_conversacion_por_participantes(base)
    qs = _safe_select_related(qs, sf, rf)

    rows, has_more, next_before_id = _apply_conversation_window(qs, request)

    if request.GET.get("autoleer") in ("1", "true", "True"):
        ids = [m.id for m in rows]
        if ids:
            _mark_qs_as_read(Mensaje.objects.filter(id__in=ids, **{rf: user}))

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

    try:
        tid = UUID(str(thread_id))
    except Exception:
        return Response({"detail": "thread_id inválido."}, status=400)

    user = request.user
    sf = _sender_field()
    rf = _recipient_field()

    if not Mensaje.objects.filter(thread_id=tid).filter(
        models.Q(**{sf: user}) | models.Q(**{rf: user})
    ).exists():
        return Response({"detail": "No autorizado o hilo inexistente."}, status=404)

    qs = Mensaje.objects.filter(thread_id=tid)
    qs = _safe_select_related(qs, sf, rf)

    rows, has_more, next_before_id = _apply_conversation_window(qs, request)

    if request.GET.get("autoleer") in ("1", "true", "True"):
        ids = [m.id for m in rows]
        if ids:
            _mark_qs_as_read(Mensaje.objects.filter(id__in=ids, **{rf: user}))

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

    try:
        tid = UUID(str(thread_id))
    except Exception:
        return Response({"detail": "thread_id inválido."}, status=400)

    user = request.user
    sf = _sender_field()
    rf = _recipient_field()

    if not Mensaje.objects.filter(thread_id=tid).filter(
        models.Q(**{sf: user}) | models.Q(**{rf: user})
    ).exists():
        return Response({"detail": "No autorizado o hilo inexistente."}, status=404)

    updated = _mark_qs_as_read(Mensaje.objects.filter(thread_id=tid, **{rf: user}))
    return Response({"ok": True, "actualizados": updated}, status=200)


# ===================== Responder =====================
@csrf_exempt
@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser])
def responder_mensaje(request):
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
        original = Mensaje.objects.get(id=mensaje_id)
    except Mensaje.DoesNotExist:
        return Response({"detail": "Mensaje no encontrado."}, status=404)

    sf = _sender_field()
    rf = _recipient_field()
    cf = _curso_field()

    if getattr(original, rf, None) != request.user:
        return Response({"detail": "No podés responder un mensaje que no recibiste."}, status=403)

    if not asunto:
        if getattr(original, "asunto", None):
            asunto = f"Re: {original.asunto}"
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

    if cf:
        nuevo_kwargs[cf] = getattr(original, cf, None)

    if _has_field(Mensaje, "reply_to"):
        nuevo_kwargs["reply_to"] = original

    if _threads_enabled():
        if not getattr(original, "thread_id", None):
            original.thread_id = uuid4()
            original.save(update_fields=["thread_id"])
        nuevo_kwargs["thread_id"] = getattr(original, "thread_id", None)

    if _has_field(Mensaje, "tipo_remitente"):
        nuevo_kwargs["tipo_remitente"] = _infer_tipo_remitente(request.user)

    if _has_field(Mensaje, "fecha_envio"):
        nuevo_kwargs["fecha_envio"] = timezone.now()

    nuevo = Mensaje.objects.create(**nuevo_kwargs)

    has_leido = _has_field(Mensaje, "leido")
    has_leido_en = _has_field(Mensaje, "leido_en")
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
            "ok": True,
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

    has_leido = _has_field(Mensaje, "leido")
    has_leido_en = _has_field(Mensaje, "leido_en")

    if not (has_leido and has_leido_en):
        return Response({"ok": True, "actualizados": 0, "scope": "self" if not scope_all else "all"}, status=200)

    base_qs = Mensaje.objects.all() if scope_all else _qs_inbox_for_user(request.user)
    updated = base_qs.filter(leido=True, leido_en__isnull=True).update(leido_en=timezone.now())
    return Response({"ok": True, "actualizados": updated, "scope": "all" if scope_all else "self"}, status=200)
