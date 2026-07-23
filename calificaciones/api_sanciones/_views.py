# calificaciones/api_sanciones/_views.py
from __future__ import annotations

from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt

from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    parser_classes,
)
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from ..jwt_auth import CookieJWTAuthentication as JWTAuthentication

from ..models import Alumno, Sancion, Notificacion
from ..schools import get_request_school, scope_queryset_to_school
from ..serializers import SancionPublicSerializer
from ..signatures import claim_signature
from ..utils_cursos import resolve_course_reference
from ..utils_pagination import paginate_queryset

from ._helpers import (
    User,
    _resolver_alumno_id,
    _authorize_reader_for_alumno,
    _is_directivo_user,
    _filter_sanciones_por_curso,
    _is_docente_o_preceptor,
    _get_payload,
    _authorize_staff_for_alumno,
    _user_label,
    _alumno_fullname,
    _course_name,
    _course_meta,
    _authorize_padre_or_admin,
)


# =========================================================
# API
# =========================================================
@csrf_exempt
@api_view(["GET", "POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def sanciones_lista_crear(request):
    """
    GET /api/sanciones/?alumno=ID|LEGAJO&school_course_id=14
      → lista filtrada

    POST /api/sanciones/
      JSON: { alumno | alumno_id | id_alumno, fecha?, asunto?, mensaje?, tipo? }

    Alias admitidos:
      - "asunto" -> Sancion.detalle
      - "mensaje" -> Sancion.motivo
    """
    active_school = get_request_school(request)

    if request.method == "GET":
        alumno_q = request.query_params.get("alumno")
        school_course_ref, curso_q, course_error = resolve_course_reference(
            school=active_school,
            raw_course=request.query_params.get("curso"),
            raw_school_course_id=request.query_params.get("school_course_id"),
            required=False,
        )
        if course_error:
            return Response({"detail": course_error}, status=400)

        qs = scope_queryset_to_school(
            Sancion.objects.all().select_related("alumno", "alumno__school_course"),
            active_school,
        ).order_by("-fecha", "-id")

        if alumno_q:
            alum = _resolver_alumno_id(alumno_q, school=active_school)
            if not alum:
                return Response({"detail": "Alumno no encontrado."}, status=404)
            if not _authorize_reader_for_alumno(request.user, alum):
                return Response({"detail": "No autorizado."}, status=403)
            qs = qs.filter(alumno=alum)
        elif not (getattr(request.user, "is_superuser", False) or _is_directivo_user(request.user)):
            return Response({"detail": "No autorizado."}, status=403)

        if curso_q or school_course_ref is not None:
            qs = _filter_sanciones_por_curso(
                qs,
                curso_q,
                school=active_school,
                school_course=school_course_ref,
            )

        items, pagination = paginate_queryset(qs, request)
        data = SancionPublicSerializer(items, many=True).data
        return Response({"results": data, **pagination}, status=200)

    # POST
    if not _is_docente_o_preceptor(request.user):
        return Response({"detail": "No autorizado."}, status=403)

    payload = _get_payload(request)

    alumno_val = payload.get("alumno", payload.get("alumno_id", payload.get("id_alumno")))
    alumno = _resolver_alumno_id(alumno_val, school=active_school)
    if not alumno:
        return Response({"detail": "Debés indicar un alumno válido."}, status=400)

    if not _authorize_staff_for_alumno(request.user, alumno):
        return Response({"detail": "No autorizado para ese alumno."}, status=403)

    asunto = (payload.get("asunto") or payload.get("detalle") or "").strip()
    mensaje = (payload.get("mensaje") or payload.get("motivo") or "").strip()
    fecha_s = (payload.get("fecha") or "").strip()
    tipo = (payload.get("tipo") or "").strip()

    if not mensaje:
        return Response({"detail": "El campo mensaje es requerido."}, status=400)

    if fecha_s:
        fecha = parse_date(fecha_s)
        if not fecha:
            return Response({"detail": "fecha inválida (formato YYYY-MM-DD)."}, status=400)
    else:
        fecha = timezone.localdate()

    docente = (payload.get("docente") or "").strip() or _user_label(request.user)
    school_ref = active_school or getattr(alumno, "school", None)

    sancion = Sancion.objects.create(
        school=school_ref,
        alumno=alumno,
        fecha=fecha,
        motivo=mensaje,
        detalle=asunto or None,
        tipo=tipo or getattr(Sancion, "TIPOS", [("Amonestación", "Amonestación")])[0][0],
        docente=docente or None,
    )

    # =========================================================
    # Notificación a padre/alumno (campanita): SIN crear Mensaje
    # =========================================================
    notificado = False
    notif_error = None
    notif_destinatario_id = None
    notif_source = None

    try:
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

        # Padre explícito
        _add(getattr(alumno, "padre", None))

        # Alumno explícito (campo Alumno.usuario)
        alumno_usuario = getattr(alumno, "usuario", None)
        _add(alumno_usuario)

        # Alumno por convención username==legajo/id_alumno
        try:
            legajo = (getattr(alumno, "id_alumno", "") or "").strip()
            alumno_username = str(getattr(alumno_usuario, "username", "") or "").strip().lower()
            if legajo and alumno_username != legajo.lower():
                u_alumno = User.objects.filter(username__iexact=legajo).first()
                _add(u_alumno)
        except Exception:
            pass

        if destinatarios:
            alumno_nombre = _alumno_fullname(alumno)
            course_name = _course_name(alumno)

            alumno_id = getattr(alumno, "id", "")

            fecha_n = getattr(sancion, "fecha", None)
            month_key = fecha_n.strftime("%Y-%m") if fecha_n else ""
            url_base = f"/alumnos/{alumno_id}/?tab=sanciones"
            url_sanc = f"{url_base}&mes={month_key}" if month_key else url_base

            docente_u = getattr(request.user, "username", None)

            motivo = getattr(sancion, "motivo", "") or getattr(sancion, "mensaje", "") or ""
            detalle = getattr(sancion, "detalle", None) or ""
            detalle_line = detalle.strip()

            asunto_msg = f"Nueva sanción para {alumno_nombre}"

            tipo_sancion = getattr(sancion, "tipo", "") or ""
            desc_parts = []
            if tipo_sancion:
                desc_parts.append(tipo_sancion)
            if course_name:
                desc_parts.append(f"Curso {course_name}")
            if motivo:
                desc_parts.append(motivo)
            contenido_msg = " · ".join([p for p in desc_parts if p]).strip()

            notificado = False
            notif_destinatario_id = None

            for destinatario in destinatarios:
                Notificacion.objects.create(
                    school=school_ref,
                    destinatario=destinatario,
                    tipo="sancion",
                    titulo=asunto_msg,
                    descripcion=contenido_msg,
                    url=url_sanc,
                    leida=False,
                    meta={
                        "alumno_id": getattr(alumno, "id", None),
                        "alumno_legajo": getattr(alumno, "id_alumno", None),
                        **_course_meta(alumno),
                        "tipo_sancion": getattr(sancion, "tipo", None),
                        "fecha": fecha_n.isoformat() if fecha_n else None,
                        "docente": docente_u,
                        "remitente": getattr(request.user, "username", None),
                    },
                )
                notificado = True
                notif_destinatario_id = getattr(destinatario, "id", None)
                try:
                    from django.conf import settings as _s
                    if getattr(_s, "EMAIL_NOTIFICATIONS_ENABLED", True):
                        to_email = (getattr(destinatario, "email", "") or "").strip()
                        if to_email:
                            nombre_dest = (
                                getattr(destinatario, "first_name", "") or
                                getattr(destinatario, "username", "") or
                                "usuario"
                            ).strip()
                            fecha_display = fecha_n.strftime("%d/%m/%Y") if fecha_n else ""
                            lineas = [
                                f"Hola, {nombre_dest},",
                                "",
                                "Se ha registrado una sanción disciplinaria:",
                                "",
                            ]
                            if alumno_nombre:
                                lineas.append(f"Alumno/a: {alumno_nombre}")
                            if course_name:
                                lineas.append(f"Curso: {course_name}")
                            if tipo_sancion:
                                lineas.append(f"Tipo de sanción: {tipo_sancion}")
                            if fecha_display:
                                lineas.append(f"Fecha: {fecha_display}")
                            if motivo:
                                lineas.append(f"Motivo: {motivo}")
                            lineas += ["", "Ante cualquier duda contactarse con contacto@alumnix.com.ar"]
                            from ..tasks import send_email_task
                            send_email_task.delay(
                                to_email=to_email,
                                subject="Nueva sanción registrada",
                                text="\n".join(lineas),
                            )
                except Exception:
                    pass

    except Exception as e:
        notificado = False
        notif_error = str(e)
        notif_destinatario_id = None

    resp = {
        "id": sancion.id,
        "notificado": notificado,
        "notif_destinatario_id": notif_destinatario_id,
        "notif_source": notif_source,
    }

    if (not notificado) and notif_error and (
        getattr(request.user, "is_superuser", False) or _is_directivo_user(request.user)
    ):
        resp["notif_error"] = notif_error

    return Response(resp, status=201)


@csrf_exempt
@api_view(["GET", "DELETE"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def sancion_detalle(request, pk: int):
    """
    GET /api/sanciones/<id>/   → detalle
    DELETE /api/sanciones/<id>/ → elimina
    """
    active_school = get_request_school(request)
    try:
        sanc = scope_queryset_to_school(
            Sancion.objects.select_related("alumno", "alumno__school_course"),
            active_school,
        ).get(pk=pk)
    except Sancion.DoesNotExist:
        return Response({"detail": "No encontrada."}, status=404)

    if request.method == "GET":
        if not _authorize_reader_for_alumno(request.user, sanc.alumno):
            return Response({"detail": "No autorizado."}, status=403)
        return Response(SancionPublicSerializer(sanc).data, status=200)

    if not _is_docente_o_preceptor(request.user):
        return Response({"detail": "No autorizado."}, status=403)
    if not _authorize_staff_for_alumno(request.user, sanc.alumno):
        return Response({"detail": "No autorizado para ese alumno."}, status=403)

    sanc.delete()
    return Response(status=204)


@csrf_exempt
@api_view(["GET", "POST", "PATCH"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def firmar_sancion(request, pk: int):
    active_school = get_request_school(request)
    try:
        sanc = scope_queryset_to_school(
            Sancion.objects.select_related("alumno", "alumno__school_course"),
            active_school,
        ).get(pk=pk)
    except Sancion.DoesNotExist:
        return Response({"detail": "Sanción no encontrada."}, status=404)

    if not _authorize_padre_or_admin(request.user, sanc.alumno):
        return Response({"detail": "No autorizado."}, status=403)

    if request.method == "GET":
        return Response(
            {
                "id": sanc.id,
                "alumno_id": sanc.alumno_id,
                "firmada": bool(getattr(sanc, "firmada", False)),
                "firmada_en": sanc.firmada_en.isoformat() if getattr(sanc, "firmada_en", None) else None,
            },
            status=200,
        )

    if bool(getattr(sanc, "firmada", False)):
        return Response(
            {
                "detail": "La sanción ya fue firmada.",
                "id": sanc.id,
                "alumno_id": sanc.alumno_id,
                "firmada": True,
                "firmada_en": sanc.firmada_en.isoformat() if getattr(sanc, "firmada_en", None) else None,
            },
            status=400,
        )

    if not claim_signature(sanc, user=request.user):
        return Response(
            {
                "detail": "La sanción ya fue firmada.",
                "id": sanc.id,
                "alumno_id": sanc.alumno_id,
                "firmada": True,
                "firmada_en": sanc.firmada_en.isoformat() if sanc.firmada_en else None,
            },
            status=400,
        )

    return Response(
        {
            "id": sanc.id,
            "alumno_id": sanc.alumno_id,
            "firmada": True,
            "firmada_en": sanc.firmada_en.isoformat() if sanc.firmada_en else None,
        },
        status=200,
    )
