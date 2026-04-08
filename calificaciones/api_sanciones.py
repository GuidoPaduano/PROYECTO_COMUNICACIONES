# calificaciones/api_sanciones.py
from __future__ import annotations

import json
from typing import Any, Optional

from django.contrib.auth import get_user_model
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
from .jwt_auth import CookieJWTAuthentication as JWTAuthentication

from .contexto import resolve_alumno_for_user
from .course_access import build_course_membership_q, course_ref_matches, get_assignment_course_refs
from .models import Alumno, Sancion, Notificacion, resolve_school_course_for_value
from .schools import get_request_school, scope_queryset_to_school
from .serializers import SancionPublicSerializer
from .user_groups import get_user_group_names, get_user_group_names_lower
from .utils_cursos import resolve_course_reference
# âœ… FIX CLAVE: antes no existÃ­a User y las notificaciones fallaban silenciosamente
User = get_user_model()

try:
    from .models_preceptores import PreceptorCurso, ProfesorCurso  # type: ignore
except Exception:
    PreceptorCurso = None
    ProfesorCurso = None


# =========================================================
# Helpers
# =========================================================
def _alumno_base_qs(school=None):
    return scope_queryset_to_school(
        Alumno.objects.select_related("school", "school_course", "padre", "usuario"),
        school,
    )


def _resolver_alumno_id(valor: Any, school=None) -> Optional[Alumno]:
    """
    Acepta PK (int), id_alumno (legajo) o string convertible.

    FIX SOLIDO:
    - Si viene numÃ©rico, probamos primero como PK.
    - Si ese PK no existe, caemos a id_alumno (legajo).
    Esto evita que un legajo numÃ©rico se interprete como PK incorrecto.
    """
    if valor is None:
        return None

    try:
        sv = str(valor).strip()
        if not sv:
            return None
        alumnos_qs = _alumno_base_qs(school)

        # 1) Intentar PK si es dÃ­gito
        if sv.isdigit():
            try:
                return alumnos_qs.get(pk=int(sv))
            except Alumno.DoesNotExist:
                pass

        # 2) Intentar por legajo/id_alumno (case-insensitive)
        return alumnos_qs.filter(id_alumno__iexact=sv).first()

    except Exception:
        return None


def _preceptor_course_refs(user, school=None):
    if PreceptorCurso is None:
        return []

    school_id = getattr(school, "id", None) or 0
    cache_attr = "_cached_sanciones_preceptor_refs_by_school"
    cached = getattr(user, cache_attr, None)
    if isinstance(cached, dict) and school_id in cached:
        return list(cached[school_id])

    try:
        qs = PreceptorCurso.objects.filter(preceptor=user)
        if school is not None:
            qs = scope_queryset_to_school(qs, school)
        refs = get_assignment_course_refs(qs)
    except Exception:
        refs = []

    try:
        if not isinstance(cached, dict):
            cached = {}
        cached[school_id] = tuple(refs)
        setattr(user, cache_attr, cached)
    except Exception:
        pass
    return refs


def _profesor_course_refs(user, school=None):
    if ProfesorCurso is None:
        return []

    school_id = getattr(school, "id", None) or 0
    cache_attr = "_cached_sanciones_profesor_refs_by_school"
    cached = getattr(user, cache_attr, None)
    if isinstance(cached, dict) and school_id in cached:
        return list(cached[school_id])

    try:
        qs = ProfesorCurso.objects.filter(profesor=user)
        if school is not None:
            qs = scope_queryset_to_school(qs, school)
        refs = get_assignment_course_refs(qs)
    except Exception:
        refs = []

    try:
        if not isinstance(cached, dict):
            cached = {}
        cached[school_id] = tuple(refs)
        setattr(user, cache_attr, cached)
    except Exception:
        pass
    return refs


def _user_label(user) -> str:
    try:
        full = (user.get_full_name() or "").strip()
        if full:
            return full
        return (getattr(user, "username", "") or "").strip()
    except Exception:
        return ""


def _course_name(alumno: Alumno | None) -> str:
    school_course = getattr(alumno, "school_course", None) if alumno is not None else None
    return (
        getattr(school_course, "name", None)
        or getattr(school_course, "code", None)
        or getattr(alumno, "curso", "")
        or ""
    )


def _course_meta(alumno: Alumno | None) -> dict[str, Any]:
    return {
        "school_course_id": getattr(alumno, "school_course_id", None) if alumno is not None else None,
        "school_course_name": _course_name(alumno),
    }


def _filter_sanciones_por_curso(qs, curso: str, *, school=None, school_course=None):
    curso = str(curso or "").strip()
    resolved_school_course = school_course
    if not curso and resolved_school_course is not None:
        curso = str(getattr(resolved_school_course, "code", "") or "").strip()
    if not curso and resolved_school_course is None:
        return qs

    if resolved_school_course is None and school is not None:
        resolved_school_course = resolve_school_course_for_value(school=school, curso=curso)
    course_q = build_course_membership_q(
        school_course_id=getattr(resolved_school_course, "id", None),
        course_code=curso,
        school_course_field="alumno__school_course",
        code_field="alumno__curso",
    )
    if course_q is None:
        return qs.none()
    return qs.filter(course_q)


def _is_docente_o_preceptor(user) -> bool:
    try:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True
        groups = get_user_group_names_lower(user)
        joined = " ".join(groups)
        return ("preceptor" in joined) or ("profesor" in joined) or ("docente" in joined) or ("directivo" in joined)
    except Exception:
        return False


def _is_directivo_user(user) -> bool:
    try:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        groups = set(get_user_group_names(user))
        return "Directivos" in groups or "Directivo" in groups
    except Exception:
        return False


def _preceptor_can_access_alumno(user, alumno: Alumno) -> bool:
    try:
        refs = _preceptor_course_refs(user, school=getattr(alumno, "school", None))
        return course_ref_matches(refs, obj=alumno)
    except Exception:
        return False


def _profesor_can_access_alumno(user, alumno: Alumno) -> bool:
    try:
        refs = _profesor_course_refs(user, school=getattr(alumno, "school", None))
        return course_ref_matches(refs, obj=alumno)
    except Exception:
        return False


def _authorize_staff_for_alumno(user, alumno: Alumno) -> bool:
    try:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False) or _is_directivo_user(user):
            return True
        groups = set(get_user_group_names_lower(user))
        joined = " ".join(groups)
        if "preceptor" in joined:
            return _preceptor_can_access_alumno(user, alumno)
        if ("profesor" in joined) or ("docente" in joined):
            return _profesor_can_access_alumno(user, alumno)
    except Exception:
        return False
    return False


def _authorize_padre_or_admin(user, alumno: Alumno) -> bool:
    try:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True
        return getattr(alumno, "padre_id", None) == getattr(user, "id", None)
    except Exception:
        return False


def _authorize_reader_for_alumno(user, alumno: Alumno) -> bool:
    if _authorize_padre_or_admin(user, alumno):
        return True
    if _authorize_staff_for_alumno(user, alumno):
        return True
    try:
        resolved = resolve_alumno_for_user(user, school=getattr(alumno, "school", None))
        return bool(resolved.alumno and resolved.alumno.id == alumno.id)
    except Exception:
        return False


def _alumno_fullname(a: Alumno) -> str:
    nm = (getattr(a, "nombre", "") or "").strip()
    # Fallback defensivo por si apellido no existe o viene vacio
    ap = (getattr(a, "apellido", "") or "").strip()
    full = (f"{ap}, {nm}").strip(", ").strip()
    return full or nm or str(getattr(a, "id_alumno", "")) or "Alumno"


def _get_payload(request) -> dict:
    """
    Devuelve payload como dict, tolerante a JSON / form-data.
    """
    try:
        if hasattr(request, "data"):
            # request.data puede ser QueryDict
            if isinstance(request.data, dict):
                return dict(request.data)
            return request.data
    except Exception:
        pass

    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return {}


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
      â†’ lista filtrada

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

        data = SancionPublicSerializer(qs, many=True).data
        return Response({"results": data}, status=200)

    # POST
    if not _is_docente_o_preceptor(request.user):
        return Response({"detail": "No autorizado."}, status=403)

    payload = _get_payload(request)

    alumno_val = payload.get("alumno", payload.get("alumno_id", payload.get("id_alumno")))
    alumno = _resolver_alumno_id(alumno_val, school=active_school)
    if not alumno:
        return Response({"detail": "DebÃ©s indicar un alumno vÃ¡lido."}, status=400)

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
            return Response({"detail": "fecha invÃ¡lida (formato YYYY-MM-DD)."}, status=400)
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
        tipo=tipo or getattr(Sancion, "TIPOS", [("AmonestaciÃ³n", "AmonestaciÃ³n")])[0][0],
        docente=docente or None,
    )

    # =========================================================
    # NotificaciÃ³n a padre/alumno (campanita): SIN crear Mensaje
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

        # Padre explÃ­cito
        _add(getattr(alumno, "padre", None))

        # Alumno explÃ­cito (campo Alumno.usuario)
        alumno_usuario = getattr(alumno, "usuario", None)
        _add(alumno_usuario)

        # Alumno por convenciÃ³n username==legajo/id_alumno
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

            asunto_msg = f"Nueva sanciÃ³n para {alumno_nombre}"

            contenido_msg = (
                "Se registrÃ³ una sanciÃ³n disciplinaria.\n\n"
                f"Alumno: {alumno_nombre}\n"
                + (f"Curso: {course_name}\n" if course_name else "")
                + f"Tipo: {getattr(sancion, 'tipo', '')}\n"
                + (f"Fecha: {fecha_n.isoformat()}\n" if fecha_n else "")
                + (f"Docente: {docente_u}\n" if docente_u else "")
                + (detalle_line + "\n" if detalle_line else "")
                + f"Motivo: {motivo}"
            ).strip()

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
    GET /api/sanciones/<id>/   â†’ detalle
    DELETE /api/sanciones/<id>/ â†’ elimina
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
        return Response({"detail": "SanciÃ³n no encontrada."}, status=404)

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
                "detail": "La sanciÃ³n ya fue firmada.",
                "id": sanc.id,
                "alumno_id": sanc.alumno_id,
                "firmada": True,
                "firmada_en": sanc.firmada_en.isoformat() if getattr(sanc, "firmada_en", None) else None,
            },
            status=400,
        )

    sanc.firmada = True
    sanc.firmada_en = timezone.now()
    sanc.firmada_por = request.user
    sanc.save(update_fields=["firmada", "firmada_en", "firmada_por"])

    return Response(
        {
            "id": sanc.id,
            "alumno_id": sanc.alumno_id,
            "firmada": True,
            "firmada_en": sanc.firmada_en.isoformat() if sanc.firmada_en else None,
        },
        status=200,
    )


