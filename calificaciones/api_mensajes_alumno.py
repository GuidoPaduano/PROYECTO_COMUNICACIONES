# calificaciones/api_mensajes_alumno.py
from __future__ import annotations

from typing import Optional

from django.contrib.auth.models import User
from django.core.exceptions import FieldDoesNotExist
from django.db import transaction
from django.utils import timezone

from rest_framework.decorators import api_view, authentication_classes, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
from .jwt_auth import CookieJWTAuthentication as JWTAuthentication
from rest_framework.response import Response

from .course_access import filter_assignments_for_course
from .models import Alumno, Mensaje, Notificacion, resolve_school_course_for_value
from .resend_email import send_message_email
from .schools import get_request_school, get_unique_alumno_by_legajo, scope_queryset_to_school
from .user_groups import get_first_user_group_name, get_user_group_names
from .utils_cursos import resolve_course_reference

try:
    from .models_preceptores import PreceptorCurso, ProfesorCurso
except Exception:
    PreceptorCurso = None
    ProfesorCurso = None


# =========================================================
# Helpers
# =========================================================
PROF_GROUPS = ["Profesor", "Profesores", "Docente", "Docentes"]
PREC_GROUPS = ["Preceptor", "Preceptores"]


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


def _course_code_from_context(*, alumno: Alumno | None = None, school_course=None, curso: str = "") -> str:
    alumno_school_course = getattr(alumno, "school_course", None) if alumno is not None else None
    return str(
        getattr(school_course, "code", None)
        or getattr(alumno_school_course, "code", None)
        or getattr(alumno, "curso", None)
        or curso
        or ""
    ).strip()


def _course_name(alumno: Alumno | None = None, *, school_course=None, curso: str = "") -> str:
    school_course = school_course or getattr(alumno, "school_course", None)
    return (
        getattr(school_course, "name", None)
        or getattr(school_course, "code", None)
        or getattr(alumno, "curso", None)
        or curso
        or ""
    )


def _course_context(*, alumno: Alumno | None = None, school_course=None, curso: str = "", school=None):
    school_course = school_course or (getattr(alumno, "school_course", None) if alumno is not None else None)
    course_code = _course_code_from_context(alumno=alumno, school_course=school_course, curso=curso)
    if school_course is None and course_code and school is not None:
        school_course = resolve_school_course_for_value(school=school, curso=course_code)
    return {
        "school_course": school_course,
        "school_course_id": getattr(school_course, "id", None),
        "school_course_name": _course_name(alumno, school_course=school_course, curso=course_code),
    }


def _user_to_dict(u: User, grupo_hint: str = ""):
    nombre = (u.get_full_name() or u.username or f"usuario-{u.id}").strip()
    return {
        "id": u.id,
        "nombre": nombre,
        "username": u.username,
        "grupo": grupo_hint or get_first_user_group_name(u, ""),
    }


def _infer_alumno_for_user(user: User, school=None) -> Optional[Alumno]:
    """Intenta inferir el Alumno asociado a este user (usuario o padre)."""
    school_id = getattr(school, "id", None) or 0
    cached = getattr(user, "_cached_inferred_alumno_by_school", None)
    if isinstance(cached, dict) and school_id in cached:
        return cached[school_id]

    qs = scope_queryset_to_school(
        Alumno.objects.select_related("school", "school_course"),
        school,
    )

    alumno = None

    if alumno is None:
        try:
            alumno = qs.filter(usuario=user).first() if _has_field(Alumno, "usuario") else None
        except Exception:
            alumno = None

    if alumno is None:
        try:
            username = (getattr(user, "username", "") or "").strip()
            if username:
                alumno = get_unique_alumno_by_legajo(username, school=school)
        except Exception:
            alumno = None

    if alumno is None:
        try:
            alumno = qs.filter(padre=user).order_by("id").first()
        except Exception:
            alumno = None

    if alumno is None:
        try:
            full = (user.get_full_name() or "").strip()
            if full:
                alumno = qs.filter(nombre__iexact=full).order_by("id").first()
        except Exception:
            alumno = None

    try:
        if not isinstance(cached, dict):
            cached = {}
        cached[school_id] = alumno
        setattr(user, "_cached_inferred_alumno_by_school", cached)
    except Exception:
        pass

    return alumno


def _school_assignment_qs(model, school=None, school_course=None, curso: str = ""):
    if model is None:
        return None
    qs = scope_queryset_to_school(model.objects.all(), school)
    school_course_id = getattr(school_course, "id", None)
    course_code = _course_code_from_context(school_course=school_course, curso=curso)
    if school_course_id is not None or course_code:
        qs = filter_assignments_for_course(
            qs,
            school=school,
            school_course_id=school_course_id,
            course_code=course_code,
        )
    return qs


def _school_has_assignment_data(school=None) -> bool:
    for model in (ProfesorCurso, PreceptorCurso):
        qs = _school_assignment_qs(model, school=school)
        if qs is None:
            continue
        try:
            if qs.exists():
                return True
        except Exception:
            continue
    return False


def _allowed_docentes_qs(*, school=None, school_course=None, curso: str = "", alumno: Optional[Alumno] = None):
    """
    Usa asignaciones por school/curso cuando existen.
    Si todavia no hay asignaciones cargadas para ese school, cae al listado general.
    """
    base = User.objects.filter(is_active=True, groups__name__in=(PROF_GROUPS + PREC_GROUPS)).distinct()
    user_ids = set()

    qs_prof = _school_assignment_qs(ProfesorCurso, school=school, school_course=school_course, curso=curso)
    if qs_prof is not None:
        if alumno is not None:
            qs_prof = filter_assignments_for_course(qs_prof, obj=alumno, school=school)
        user_ids.update(uid for uid in qs_prof.values_list("profesor_id", flat=True) if uid is not None)

    qs_prec = _school_assignment_qs(PreceptorCurso, school=school, school_course=school_course, curso=curso)
    if qs_prec is not None:
        if alumno is not None:
            qs_prec = filter_assignments_for_course(qs_prec, obj=alumno, school=school)
        user_ids.update(uid for uid in qs_prec.values_list("preceptor_id", flat=True) if uid is not None)

    if user_ids:
        return base.filter(id__in=user_ids)
    if not _school_has_assignment_data(school=school):
        return base
    return base.none()


def _allowed_docentes_list(*, school=None, school_course=None, curso: str = "", alumno: Optional[Alumno] = None):
    return list(
        _allowed_docentes_qs(
            school=school,
            school_course=school_course,
            curso=curso,
            alumno=alumno,
        ).prefetch_related("groups")
    )


# =========================================================
# GET: destinatarios (alumno) → lista de docentes/preceptores
# =========================================================
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def docentes_destinatarios(request):
    user = request.user
    active_school = get_request_school(request)

    alumno = _infer_alumno_for_user(user, school=active_school)
    school_course_ref, curso, course_error = resolve_course_reference(
        school=active_school,
        raw_course=request.GET.get("curso"),
        raw_school_course_id=request.GET.get("school_course_id"),
        required=False,
    )
    if course_error:
        return Response({"detail": course_error}, status=400)

    alumno_school_course_id = getattr(alumno, "school_course_id", None) if alumno is not None else None
    alumno_course_code = _course_code_from_context(alumno=alumno)
    if school_course_ref is not None and alumno_school_course_id is not None and school_course_ref.id != alumno_school_course_id:
        return Response({"detail": "El school_course_id no coincide con el alumno activo."}, status=400)
    if curso and alumno_course_code and curso != alumno_course_code:
        return Response({"detail": "El curso enviado no coincide con el alumno activo."}, status=400)

    if not curso:
        if alumno and alumno_course_code:
            curso = alumno_course_code
            school_course_ref = school_course_ref or getattr(alumno, "school_course", None)

    users = _allowed_docentes_list(
        school=active_school,
        school_course=school_course_ref or getattr(alumno, "school_course", None),
        curso=curso,
        alumno=alumno,
    )
    course_context = _course_context(alumno=alumno, school_course=school_course_ref, curso=curso, school=active_school)

    prof_group_names = {name.lower() for name in PROF_GROUPS}
    prec_group_names = {name.lower() for name in PREC_GROUPS}
    profs = []
    precs = []
    for receptor in users:
        lowered = {name.lower() for name in get_user_group_names(receptor)}
        if lowered.intersection(prof_group_names):
            profs.append(receptor)
        if lowered.intersection(prec_group_names):
            precs.append(receptor)

    return Response(
        {
            "school_course_id": course_context["school_course_id"],
            "school_course_name": course_context["school_course_name"],
            "profesores": [_user_to_dict(u, "Profesor") for u in profs],
            "preceptores": [_user_to_dict(u, "Preceptor") for u in precs],
            "results": [_user_to_dict(u) for u in users],
        },
        status=200,
    )


# =========================================================
# POST: enviar (alumno → docente/preceptor)
# =========================================================
@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def alumno_enviar(request):
    """
    Cuerpo esperado:
    {
        "receptor_id": 123,     // obligatorio
        "asunto": "Consulta",   // obligatorio
        "contenido": "Hola...", // obligatorio
        "school_course_id": 14  // opcional; si no se envía, se infiere del alumno activo
    }
    """
    user = request.user
    active_school = get_request_school(request)
    data = request.data or {}

    receptor_id = data.get("receptor_id")
    asunto = (data.get("asunto") or "").strip()
    contenido = (data.get("contenido") or "").strip()
    alumno = _infer_alumno_for_user(user, school=active_school)
    school_course_ref, curso, course_error = resolve_course_reference(
        school=active_school,
        raw_course=data.get("curso"),
        raw_school_course_id=data.get("school_course_id"),
        required=False,
    )

    if not receptor_id or not asunto or not contenido:
        return Response(
            {"detail": "Faltan datos: receptor_id, asunto y contenido son obligatorios."},
            status=400,
        )
    if course_error:
        return Response({"detail": course_error}, status=400)

    # Validar receptor
    try:
        receptor = User.objects.get(id=receptor_id, is_active=True)
    except User.DoesNotExist:
        return Response({"detail": "El destinatario no existe."}, status=404)

    grupos_receptor = set(get_user_group_names(receptor))
    if not (grupos_receptor.intersection(PROF_GROUPS) or grupos_receptor.intersection(PREC_GROUPS)):
        return Response({"detail": "El destinatario no es Profesor/Preceptor habilitado."}, status=403)

    # Inferir curso y alumno, si se puede
    alumno_school_course_id = getattr(alumno, "school_course_id", None) if alumno is not None else None
    alumno_course_code = _course_code_from_context(alumno=alumno)
    if school_course_ref is not None and alumno_school_course_id is not None and school_course_ref.id != alumno_school_course_id:
        return Response({"detail": "El school_course_id no coincide con el alumno activo."}, status=400)
    if curso and alumno_course_code and curso != alumno_course_code:
        return Response({"detail": "El curso enviado no coincide con el alumno activo."}, status=400)

    if not curso:
        if alumno and alumno_course_code:
            curso = alumno_course_code
            school_course_ref = school_course_ref or getattr(alumno, "school_course", None)

    school_ref = active_school or getattr(alumno, "school", None)
    allowed_receptores = _allowed_docentes_list(
        school=school_ref,
        school_course=school_course_ref or getattr(alumno, "school_course", None),
        curso=curso,
        alumno=alumno,
    )
    if not any(getattr(allowed, "id", None) == receptor.id for allowed in allowed_receptores):
        return Response({"detail": "El destinatario no esta habilitado para el colegio o curso activo."}, status=403)
    course_context = _course_context(alumno=alumno, school_course=school_course_ref, curso=curso, school=school_ref)
    school_course_ref = course_context["school_course"] or school_course_ref
    course_code = _course_code_from_context(alumno=alumno, school_course=school_course_ref, curso=curso)

    sf = _sender_field()
    rf = _recipient_field()

    kwargs = {
        sf: user,
        rf: receptor,
        "asunto": asunto[:255],
        "contenido": contenido,
    }

    if _has_field(Mensaje, "school") and school_ref is not None:
        kwargs["school"] = school_ref

    if course_code:
        kwargs["curso"] = course_code

    if _has_field(Mensaje, "alumno") and alumno is not None:
        kwargs["alumno"] = alumno

    if _has_field(Mensaje, "school_course"):
        if school_course_ref is not None:
            kwargs["school_course"] = school_course_ref
        elif alumno is not None and getattr(alumno, "school_course", None) is not None:
            kwargs["school_course"] = getattr(alumno, "school_course", None)
        elif course_code and school_ref is not None:
            school_course = resolve_school_course_for_value(school=school_ref, curso=course_code)
            if school_course is not None:
                kwargs["school_course"] = school_course

    if _has_field(Mensaje, "fecha_envio"):
        kwargs["fecha_envio"] = timezone.now()

    with transaction.atomic():
        msg = Mensaje.objects.create(**kwargs)

    # Notificacion campanita para el docente/preceptor receptor
    try:
        contenido_corto = (contenido[:160] + "...") if len(contenido) > 160 else contenido
        url = "/mensajes"
        if hasattr(msg, "thread_id") and getattr(msg, "thread_id", None):
            url = f"/mensajes/hilo/{getattr(msg, 'thread_id')}"
        actor_label = (user.get_full_name() or user.username or "Usuario").strip()
        titulo = f"{actor_label}: {asunto}" if asunto else f"Nuevo mensaje de {actor_label}"
        Notificacion.objects.create(
            school=school_ref,
            destinatario=receptor,
            tipo="mensaje",
            titulo=titulo,
            descripcion=contenido_corto.strip() or None,
            url=url,
            leida=False,
            meta={
                "mensaje_id": getattr(msg, "id", None),
                "thread_id": str(getattr(msg, "thread_id", "")) if hasattr(msg, "thread_id") else str(getattr(msg, "id", "")),
                "school_course_id": getattr(msg, "school_course_id", None),
                "school_course_name": course_context["school_course_name"],
                "remitente_id": getattr(user, "id", None),
                "alumno_id": getattr(alumno, "id", None) if alumno else None,
            },
        )
    except Exception:
        pass

    try:
        to_email = (getattr(receptor, "email", "") or "").strip()
        if to_email:
            actor_label = (user.get_full_name() or user.username or "Usuario").strip()
            send_message_email(
                to_email=to_email,
                subject=(asunto or "Nuevo mensaje").strip(),
                content=(contenido or "").strip(),
                actor_label=actor_label,
            )
    except Exception:
        pass

    # Respuesta estable para el front actual
    return Response(
        {
            "id": msg.id,
            "asunto": getattr(msg, "asunto", ""),
            "contenido": getattr(msg, "contenido", ""),
            "school_course_id": getattr(msg, "school_course_id", None),
            "school_course_name": course_context["school_course_name"],
            "fecha_envio": getattr(msg, "fecha_envio", None),
            "emisor": _user_to_dict(user),
            "receptor": _user_to_dict(receptor),
            "emisor_id": getattr(user, "id", None),
            "receptor_id": getattr(receptor, "id", None),
        },
        status=201,
    )
