# calificaciones/api_mensajes/_views.py
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
from ..jwt_auth import CookieJWTAuthentication as JWTAuthentication

from django.db import IntegrityError, models, transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

from ..models import Mensaje, Notificacion
from ..schools import get_request_school, scope_queryset_to_school
from ..utils_cursos import resolve_course_reference

from uuid import UUID, uuid4
import json

from ._helpers import (
    _flags,
    _has_field,
    _threads_enabled,
    _sender_field,
    _recipient_field,
    _course_code_for_storage,
    _alumnos_por_curso_qs,
    _serialize_msg,
    _mark_qs_as_read,
    _message_is_unread,
    _user_is_alumno_or_padre,
    _user_can_filter_inbox_by_alumno,
    _filter_messages_for_alumno,
    _coerce_json,
    _get_user_by_id,
    _get_alumno_by_any_id_prefetched,
    _qs_inbox_for_user,
    _infer_tipo_remitente,
    _unique_users,
    _fallback_user_for_alumno,
    _notif_url_for_msg,
    _notify_msg,
    _apply_conversation_window,
    _qs_conversacion_por_participantes,
    _normalize_subject,
    _get_curso_value,
    _get_school_course_id_value,
    _get_school_course_name_value,
    _authorize_staff_for_alumno,
    _authorize_staff_for_course,
    _staff_can_send_schoolwide,
    _message_base_queryset,
    _select_message_related,
    _user_label,
    _parse_limit,
)

User = get_user_model()


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
                from ..resend_email import send_message_email
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
                contenido_msg = (getattr(msg, "contenido", "") or "").strip()
                descripcion = (contenido_msg[:160] + "…") if len(contenido_msg) > 160 else contenido_msg
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
    alumno_param = (
        request.GET.get("alumno_id")
        or request.GET.get("id_alumno")
        or request.GET.get("alumno")
    )
    if alumno_param not in (None, ""):
        alumno = _get_alumno_by_any_id_prefetched(alumno_param, school=active_school)
        if alumno is None:
            return Response({"detail": "Alumno no encontrado."}, status=404)
        if not _user_can_filter_inbox_by_alumno(request.user, alumno):
            return Response({"detail": "No autorizado para ese alumno."}, status=403)
        qs = _filter_messages_for_alumno(qs, alumno, user=request.user)
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

    if (
        destinatario == request.user
        and not getattr(request.user, "is_superuser", False)
        and _user_is_alumno_or_padre(request.user)
        and _message_is_unread(msg)
    ):
        return Response(
            {"detail": "No podés eliminar mensajes no leídos."},
            status=403,
        )

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
    alumno_param = (
        request.GET.get("alumno_id")
        or request.GET.get("id_alumno")
        or request.GET.get("alumno")
    )

    if alumno_param not in (None, ""):
        alumno = _get_alumno_by_any_id_prefetched(alumno_param, school=active_school)
        if alumno is None:
            return Response({"detail": "Alumno no encontrado."}, status=404)
        if not _user_can_filter_inbox_by_alumno(request.user, alumno):
            return Response({"detail": "No autorizado para ese alumno."}, status=403)
        qs = _filter_messages_for_alumno(qs, alumno, user=request.user)

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
    qs = _select_message_related(qs, sf, rf, "school_course", "alumno")

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

    Optimizado:
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
        qs = _select_message_related(qs, sf, rf, "school_course")

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
    qs = _select_message_related(qs, sf, rf, "school_course")

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
    qs = _select_message_related(qs, sf, rf, "school_course")

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
    raw_client_request_id = data.get("client_request_id") or data.get("clientRequestId")
    client_request_id = None
    if raw_client_request_id:
        try:
            client_request_id = UUID(str(raw_client_request_id))
        except (TypeError, ValueError, AttributeError):
            return Response({"detail": "client_request_id inválido."}, status=400)

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

    deduplicated = False
    if client_request_id is not None and _has_field(Mensaje, "client_request_id"):
        nuevo_kwargs["client_request_id"] = client_request_id
        nuevo = Mensaje.objects.filter(
            remitente=request.user,
            client_request_id=client_request_id,
        ).first()
        if nuevo is not None:
            deduplicated = True
        else:
            try:
                with transaction.atomic():
                    nuevo = Mensaje.objects.create(**nuevo_kwargs)
            except IntegrityError:
                nuevo = Mensaje.objects.get(
                    remitente=request.user,
                    client_request_id=client_request_id,
                )
                deduplicated = True
    else:
        nuevo = Mensaje.objects.create(**nuevo_kwargs)

    if deduplicated:
        same_request = (
            getattr(nuevo, f"{rf}_id", None) == getattr(original_sender, "id", None)
            and getattr(nuevo, "asunto", "") == asunto
            and getattr(nuevo, "contenido", "") == contenido
        )
        if flags["has_reply_to"]:
            same_request = same_request and getattr(nuevo, "reply_to_id", None) == original.id
        if not same_request:
            return Response(
                {"detail": "client_request_id ya fue utilizado para otra respuesta."},
                status=409,
            )

    if not deduplicated:
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
            "deduplicated": deduplicated,
        },
        status=200 if deduplicated else 201,
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
