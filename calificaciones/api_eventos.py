# calificaciones/api_eventos.py
from django.views.decorators.csrf import csrf_exempt
from django.utils.dateparse import parse_date
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction
from django.db.models import Q

from rest_framework.decorators import (
    api_view,
    permission_classes,
    authentication_classes,  # ✅ NUEVO
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .jwt_auth import CookieJWTAuthentication as JWTAuthentication

from .contexto import resolve_alumno_for_user
from .course_access import (
    build_course_membership_q,
    build_course_membership_q_for_refs,
    course_ref_matches,
    get_assignment_course_refs,
)
from .models import Evento, Notificacion, SchoolCourse, resolve_school_course_for_value
from .schools import get_request_school, scope_queryset_to_school
from .user_groups import get_user_group_names
from .utils_cursos import get_course_label, get_school_course_choices, is_curso_valido, resolve_course_reference

# Intentamos importar Alumno para validar cursos y, si se puede, detectar curso del alumno
try:
    from .models import Alumno  # type: ignore
except Exception:
    Alumno = None  # noqa: N816

User = get_user_model()

# ✅ PreceptorCurso para validar cursos asignados al preceptor
try:
    from .models_preceptores import PreceptorCurso, ProfesorCurso  # type: ignore
except Exception:
    PreceptorCurso = None  # noqa: N816
    ProfesorCurso = None  # noqa: N816


# ------------------------------------------------------------
# Helpers de roles
# ------------------------------------------------------------
def _effective_groups(request):
    """
    Respeta modo vista previa SOLO si el usuario es superuser.
    Puede venir por query (?view_as=...) o header (X-Preview-Role).
    """
    if getattr(request, "_effective_groups_resolved", False):
        return getattr(request, "_effective_groups_cache", [])

    try:
        role = (request.GET.get("view_as") or request.headers.get("X-Preview-Role") or "").strip()
    except Exception:
        role = ""

    valid = {"Profesores", "Preceptores", "Padres", "Alumnos", "Directivos"}
    if role in valid and getattr(request.user, "is_superuser", False):
        request._effective_groups_cache = [role]
        request._effective_groups_resolved = True
        return request._effective_groups_cache

    try:
        groups = list(get_user_group_names(getattr(request, "user", None)))
    except Exception:
        groups = []

    request._effective_groups_cache = groups
    request._effective_groups_resolved = True
    return groups


def _has_role(request, *roles):
    eff = set(_effective_groups(request))
    return any(r in eff for r in roles)


def _require_eventos_write_perm(request):
    # Solo roles explícitos o superuser pueden crear/editar/eliminar eventos.
    if getattr(request.user, "is_superuser", False):
        return True
    if _has_role(request, "Preceptores", "Profesores", "Directivos"):
        return True
    return False


def _collect_destinatarios_evento(curso: str, school=None, school_course=None):
    """
    Para un evento de curso, notificamos a:
    - usuario padre (Alumno.padre)
    - usuario alumno (si existe Alumno.usuario)
    - usuario por convención username==legajo/id_alumno

    Deduplicamos por user.id para no spamear si hay hermanos/duplicados.
    """
    if Alumno is None:
        return []

    destinatarios = []
    seen = set()

    # Detectar si existe el campo Alumno.usuario
    try:
        field_names = {f.name for f in Alumno._meta.fields}  # type: ignore
    except Exception:
        field_names = set()

    course_code = (
        getattr(school_course, "code", None)
        or str(curso or "").strip()
    )
    course_q = build_course_membership_q(
        school_course_id=getattr(school_course, "id", None),
        course_code=course_code,
    )
    if course_q is None:
        return []

    qs = scope_queryset_to_school(Alumno.objects.all(), school).filter(course_q)  # type: ignore
    select_related_fields = ["padre"]
    if "usuario" in field_names:
        select_related_fields.append("usuario")
    try:
        qs = qs.select_related(*select_related_fields)
    except Exception:
        pass

    legajos = []
    for a in qs:
        _add_destinatario(destinatarios, seen, getattr(a, 'padre', None))

        if 'usuario' in field_names:
            usuario = getattr(a, 'usuario', None)
            _add_destinatario(destinatarios, seen, usuario)
        else:
            usuario = None

        # username==legajo/id_alumno
        try:
            legajo = (getattr(a, 'id_alumno', '') or '').strip()
            if legajo and str(getattr(usuario, "username", "") or "").strip() != legajo:
                legajos.append(legajo)
        except Exception:
            pass

    if legajos:
        try:
            users = User.objects.filter(username__in=sorted(set(legajos)))
            by_username = {str(getattr(u, "username", "")).strip(): u for u in users}
            for leg in legajos:
                _add_destinatario(destinatarios, seen, by_username.get(leg))
        except Exception:
            pass

    return destinatarios


def _crear_notificaciones_evento(*, ev: Evento, actor, curso: str):
    """Crea notificaciones para un evento recién creado (curso completo)."""
    school_course = getattr(ev, "school_course", None)
    curso = (
        getattr(school_course, "code", None)
        or curso
        or getattr(ev, "curso", "")
        or ""
    ).strip()
    if not curso:
        return 0

    destinatarios = _collect_destinatarios_evento(
        curso,
        school=getattr(ev, "school", None),
        school_course=school_course,
    )
    if not destinatarios:
        return 0

    course_name = getattr(school_course, "name", None) or getattr(school_course, "code", None) or curso
    titulo = f"Nuevo evento en el calendario ({course_name})"

    fecha = getattr(ev, "fecha", None)
    try:
        fecha_s = fecha.isoformat() if fecha else ""
    except Exception:
        fecha_s = str(fecha) if fecha else ""

    desc = (getattr(ev, "descripcion", None) or "").strip()
    tipo = (getattr(ev, "tipo_evento", None) or "").strip()
    actor_label = _user_label(actor) or (getattr(actor, "username", "") or "").strip()

    lines = [f"Evento: {getattr(ev, 'titulo', '')}"]
    if course_name:
        lines.append(f"Curso: {course_name}")
    if tipo:
        lines.append(f"Tipo: {tipo}")
    if fecha_s:
        lines.append(f"Fecha: {fecha_s}")
    if actor_label:
        lines.append(f"Creado por: {actor_label}")
    if desc:
        lines.append("")
        lines.append(desc)

    descripcion = "\n".join(lines).strip()

    url = "/calendario"

    meta = {
        "evento_id": getattr(ev, "id", None),
        "school_course_id": getattr(ev, "school_course_id", None),
        "school_course_name": course_name,
        "fecha": fecha_s or None,
        "tipo_evento": tipo or None,
        "creado_por": actor_label or None,
    }

    notifs = []
    for u in destinatarios:
        try:
            notifs.append(
                Notificacion(
                    school=getattr(ev, "school", None),
                    destinatario=u,
                    tipo="evento",
                    titulo=titulo,
                    descripcion=descripcion,
                    url=url,
                    leida=False,
                    meta=meta,
                )
            )
        except Exception:
            pass

    if not notifs:
        return 0

    try:
        Notificacion.objects.bulk_create(notifs, batch_size=500)
        return len(notifs)
    except Exception:
        created = 0
        for n in notifs:
            try:
                n.save()
                created += 1
            except Exception:
                pass
        return created


# ------------------------------------------------------------
# Validaciones / parsing
# ------------------------------------------------------------
VALID_CURSOS = {
    "1A",
    "1B",
    "2A",
    "2B",
    "3A",
    "3B",
    "4ECO",
    "4NAT",
    "5ECO",
    "5NAT",
    "6ECO",
    "6NAT",
}
def _parse_date(q):
    q = (q or "").strip()
    return parse_date(q) if q else None


def _is_valid_curso(curso: str, school=None) -> bool:
    """
    Valida contra Alumno.CURSOS si existe; si no, acepta cualquier string no vacío.
    """
    curso = (curso or "").strip()
    if not curso:
        return False

    return is_curso_valido(curso, school=school)


def _is_valid_tipo_evento(tipo: str) -> bool:
    """
    Valida contra Evento.TIPOS_EVENTO si existe; si no, acepta cualquier string no vacío.
    """
    tipo = (tipo or "").strip()
    if not tipo:
        return False

    try:
        tipos_validos = {t[0] for t in getattr(Evento, "TIPOS_EVENTO", [])}
        if tipos_validos:
            return tipo in tipos_validos
    except Exception:
        pass

    return True


def _is_all_cursos(value: str) -> bool:
    return (value or "").strip().upper() in {"ALL", "*", "TODOS"}


def _all_cursos_disponibles(school=None):
    """
    Devuelve la lista de cursos disponibles.
    - Si Alumno.CURSOS existe, usa ese catálogo.
    - Si no, intenta obtenerlos desde la base de alumnos.
    """
    return [str(code) for code, _name in get_school_course_choices(school=school)]


def _course_ref_for_alumno_user(user, school=None):
    try:
        resolution = resolve_alumno_for_user(user, school=school)
        if resolution.alumno is not None:
            alumno = resolution.alumno
            return (
                getattr(alumno, "school_course_id", None),
                getattr(getattr(alumno, "school_course", None), "code", None)
                or getattr(alumno, "curso", None),
            )
    except Exception:
        pass
    return None, None


# ------------------------------------------------------------
# Permisos por curso para Preceptores
# ------------------------------------------------------------
def _cursos_habilitados_preceptor(user, school=None):
    """
    Devuelve lista de cursos habilitados para el preceptor.
    - Superuser: habilitado para todo.
    - Preceptor común: cursos asignados en PreceptorCurso.
    Si PreceptorCurso no está disponible, devuelve [] (modo seguro).
    """
    if getattr(user, "is_superuser", False):
        return sorted(set(_all_cursos_disponibles(school=school)))

    if PreceptorCurso is None:
        return []

    try:
        refs = _preceptor_course_refs(user, school=school)
        return sorted({ref.course_code for ref in refs if getattr(ref, "course_code", "")})
    except Exception:
        return []


def _school_course_ids_habilitados_preceptor(user, school=None):
    if getattr(user, "is_superuser", False):
        try:
            return list(
                SchoolCourse.objects.filter(school=school, is_active=True).values_list("id", flat=True)
            )
        except Exception:
            return []

    if PreceptorCurso is None:
        return []

    try:
        refs = _preceptor_course_refs(user, school=school)
        return sorted(
            {
                int(ref.school_course_id)
                for ref in refs
                if getattr(ref, "school_course_id", None) is not None
            }
        )
    except Exception:
        return []


def _preceptor_course_refs(user, school=None):
    if PreceptorCurso is None:
        return []

    school_id = getattr(school, "id", None) or 0
    cache_attr = "_cached_eventos_preceptor_refs_by_school"
    cached = getattr(user, cache_attr, None)
    if isinstance(cached, dict) and school_id in cached:
        return list(cached[school_id])

    try:
        qs = scope_queryset_to_school(PreceptorCurso.objects.filter(preceptor=user), school)
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


def _preceptor_puede_ver_curso(user, curso: str = "", school=None, school_course=None) -> bool:
    if not ((curso or "").strip() or getattr(school_course, "id", None) is not None):
        return False

    if getattr(user, "is_superuser", False):
        return True

    refs = _preceptor_course_refs(user, school=school)
    return course_ref_matches(
        refs,
        school_course_id=getattr(school_course, "id", None),
        course_code=curso,
    )


def _cursos_habilitados_profesor(user, school=None):
    """
    Devuelve cursos asignados a profesor.
    - Superuser: habilitado para todo.
    - Si no hay asignaciones, devuelve [] (sin restricciones).
    """
    if getattr(user, "is_superuser", False):
        return sorted(set(_all_cursos_disponibles(school=school)))

    if ProfesorCurso is None:
        return []

    try:
        refs = _profesor_course_refs(user, school=school)
        return sorted({ref.course_code for ref in refs if getattr(ref, "course_code", "")})
    except Exception:
        return []


def _school_course_ids_habilitados_profesor(user, school=None):
    if getattr(user, "is_superuser", False):
        try:
            return list(
                SchoolCourse.objects.filter(school=school, is_active=True).values_list("id", flat=True)
            )
        except Exception:
            return []

    if ProfesorCurso is None:
        return []

    try:
        refs = _profesor_course_refs(user, school=school)
        return sorted(
            {
                int(ref.school_course_id)
                for ref in refs
                if getattr(ref, "school_course_id", None) is not None
            }
        )
    except Exception:
        return []


def _profesor_course_refs(user, school=None):
    if ProfesorCurso is None:
        return []

    school_id = getattr(school, "id", None) or 0
    cache_attr = "_cached_eventos_profesor_refs_by_school"
    cached = getattr(user, cache_attr, None)
    if isinstance(cached, dict) and school_id in cached:
        return list(cached[school_id])

    try:
        qs = scope_queryset_to_school(ProfesorCurso.objects.filter(profesor=user), school)
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


def _profesor_puede_ver_curso(user, curso: str = "", school=None, school_course=None) -> bool:
    if not ((curso or "").strip() or getattr(school_course, "id", None) is not None):
        return False

    if getattr(user, "is_superuser", False):
        return True

    refs = _profesor_course_refs(user, school=school)
    return course_ref_matches(
        refs,
        school_course_id=getattr(school_course, "id", None),
        course_code=curso,
    )


# ------------------------------------------------------------
# Payload para selector del frontend
# ------------------------------------------------------------
def _serialize_cursos_para_selector(cursos, school=None):
    """
    Entrada: iterable de codigos de curso.
    Salida: {"cursos":[{"id":"5A","code":"5A","nombre":"5A","school_course_id": 1}, ...]}
    El frontend usa `school_course_id` como referencia principal y `code` como identificador legible.
    """
    out = []
    for c in cursos or []:
        c = (str(c) or "").strip()
        if not c:
            continue
        school_course = resolve_school_course_for_value(school=school, curso=c) if school is not None else None
        out.append(
            {
                "id": c,
                "code": c,
                "nombre": get_course_label(c, school=school),
                "school_course_id": getattr(school_course, "id", None),
            }
        )
    return {"cursos": out}


# ------------------------------------------------------------
# Serialización / tipos
# ------------------------------------------------------------
def _tipos_evento_default():
    # ✅ NUEVO: preferimos el modelo si está definido
    try:
        tipos = [t[0] for t in getattr(Evento, "TIPOS_EVENTO", [])]
        if tipos:
            return tipos
    except Exception:
        pass
    return ["examen", "acto", "reunión", "feriado"]


def _serialize_evento(ev: Evento):
    fecha = getattr(ev, "fecha", None)
    start = None
    if fecha is not None:
        try:
            start = fecha.isoformat()
        except Exception:
            start = str(fecha)

    school_course = getattr(ev, "school_course", None)
    curso = getattr(ev, "curso", "")
    curso_nombre = getattr(school_course, "name", None) or get_course_label(curso, school=getattr(ev, "school", None))

    return {
        "id": str(getattr(ev, "id", "")),
        "school_course_id": getattr(ev, "school_course_id", None),
        "school_course_name": curso_nombre,
        "title": getattr(ev, "titulo", "") or getattr(ev, "title", ""),
        "start": start,
        "extendedProps": {
            "description": getattr(ev, "descripcion", "") or getattr(ev, "description", ""),
            "school_course_name": curso_nombre,
            "school_course_id": getattr(ev, "school_course_id", None),
            "tipo_evento": getattr(ev, "tipo_evento", ""),
        },
    }


# ------------------------------------------------------------
# Notificaciones (campanita) para eventos
# ------------------------------------------------------------

def _user_label(user) -> str:
    try:
        full = (user.get_full_name() or "").strip()
        if full:
            return full
        return (getattr(user, "username", "") or "").strip() or "Usuario"
    except Exception:
        return "Usuario"


def _add_destinatario(destinatarios, seen_ids, u):
    try:
        if u is None:
            return
        uid = getattr(u, "id", None)
        if uid is None:
            return
        if uid in seen_ids:
            return
        seen_ids.add(uid)
        destinatarios.append(u)
    except Exception:
        return


def _notify_evento_creado(request, ev: Evento):
    """Crea notificaciones para el evento recién creado (curso completo)."""
    try:
        curso = (getattr(ev, 'curso', '') or '').strip()
        actor = getattr(request, 'user', None)
        _crear_notificaciones_evento(ev=ev, actor=actor, curso=curso)
    except Exception:
        return


# ------------------------------------------------------------
# Endpoints base
# ------------------------------------------------------------
def _resolve_school_course_for_event(curso: str, school=None):
    curso = (curso or "").strip()
    if not curso or _is_all_cursos(curso):
        return None
    return resolve_school_course_for_value(school=school, curso=curso)


def _event_course_q(*, school_course_id: int | None = None, course_code: str | None = None, include_all_markers: bool = False):
    return build_course_membership_q(
        school_course_id=school_course_id,
        course_code=course_code,
        school_course_field="school_course",
        code_field="curso",
        include_all_markers=include_all_markers,
    )


@csrf_exempt
@api_view(["GET"])
@authentication_classes([JWTAuthentication])  # ✅ NUEVO
@permission_classes([IsAuthenticated])
def eventos_listar(request):
    """
    Lista eventos.

    Query params:
    - school_course_id=... (referencia principal para un curso puntual)
    - curso=ALL (marcador especial para vista global donde corresponda)
    - desde=YYYY-MM-DD (opcional)
    - hasta=YYYY-MM-DD (opcional)

    Reglas:
    - Alumnos: intenta usar su curso automáticamente; si no se puede detectar, sólo admite el marcador global ALL.
    - Preceptores y Profesores: con school_course_id filtra un curso; sin filtro o con ALL lista sus cursos habilitados.
    - Directivos/Admin: con school_course_id filtra un curso; sin filtro o con ALL lista todo.
    """
    active_school = get_request_school(request)
    qs = scope_queryset_to_school(
        Evento.objects.select_related("school_course", "school"),
        active_school,
    )

    desde = _parse_date(request.GET.get("desde"))
    hasta = _parse_date(request.GET.get("hasta"))
    if desde:
        qs = qs.filter(fecha__gte=desde)
    if hasta:
        qs = qs.filter(fecha__lte=hasta)

    selected_school_course, curso, course_error = resolve_course_reference(
        school=active_school,
        raw_course=request.GET.get("curso"),
        raw_school_course_id=request.GET.get("school_course_id"),
        required=False,
        allow_all_markers=True,
    )
    if course_error:
        return Response({"detail": course_error}, status=status.HTTP_400_BAD_REQUEST)
    selected_school_course_id = getattr(selected_school_course, "id", None)

    if _has_role(request, "Alumnos"):
        alumno_school_course_id, curso_auto = _course_ref_for_alumno_user(request.user, school=active_school)
        if curso_auto:
            curso = curso_auto
            selected_school_course_id = alumno_school_course_id
        elif not curso:
            return Response(
                {"detail": "Falta el parámetro 'curso' para alumnos (no se pudo detectar automáticamente)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    elif _has_role(request, "Preceptores"):
        # ✅ Preceptores pueden listar todos los cursos si no pasan curso o si piden "ALL"
        if _is_all_cursos(curso):
            curso = ""
            selected_school_course = None
            selected_school_course_id = None
        if selected_school_course_id is not None or curso:
            if not _preceptor_puede_ver_curso(
                request.user,
                curso,
                school=active_school,
                school_course=selected_school_course,
            ):
                return Response(
                    {"detail": "No tenés permiso para ver eventos de este curso."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        else:
            preceptor_refs = _preceptor_course_refs(request.user, school=active_school)
            if not preceptor_refs:
                return Response(
                    {"detail": "No tenes cursos asignados para ver eventos."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            course_q = build_course_membership_q_for_refs(
                preceptor_refs,
                school_course_field="school_course",
                code_field="curso",
                include_all_markers=True,
            )
            if course_q is None:
                return Response(
                    {"detail": "No tenes cursos asignados para ver eventos."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            qs = qs.filter(course_q)
    elif _has_role(request, "Profesores"):
        profesor_refs = _profesor_course_refs(request.user, school=active_school)
        if _is_all_cursos(curso):
            curso = ""
            selected_school_course = None
            selected_school_course_id = None
        if selected_school_course_id is not None or curso:
            if not profesor_refs:
                return Response(
                    {"detail": "No tenes cursos asignados para ver eventos."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if not _profesor_puede_ver_curso(
                request.user,
                curso,
                school=active_school,
                school_course=selected_school_course,
            ):
                return Response(
                    {"detail": "No tenés permiso para ver eventos de este curso."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        else:
            if not profesor_refs:
                return Response(
                    {"detail": "No tenes cursos asignados para ver eventos."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            course_q = build_course_membership_q_for_refs(
                profesor_refs,
                school_course_field="school_course",
                code_field="curso",
                include_all_markers=True,
            )
            if course_q is None:
                return Response(
                    {"detail": "No tenes cursos asignados para ver eventos."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            qs = qs.filter(course_q)

    if curso and _is_all_cursos(curso):
        curso = ""
        selected_school_course = None
        selected_school_course_id = None
    if selected_school_course_id is not None or curso:
        if selected_school_course_id is None and not _is_valid_curso(curso, school=active_school):
            return Response({"detail": "Curso inválido."}, status=status.HTTP_400_BAD_REQUEST)
        selected_school_course_id = selected_school_course_id or getattr(selected_school_course, "id", None)
        course_q = _event_course_q(
            school_course_id=selected_school_course_id,
            course_code=curso,
            include_all_markers=True,
        )
        if course_q is None:
            return Response({"detail": "Curso invÃ¡lido."}, status=status.HTTP_400_BAD_REQUEST)
        qs = qs.filter(course_q)

    qs = qs.order_by("fecha", "id")
    data = [_serialize_evento(e) for e in qs]
    return Response(data, status=status.HTTP_200_OK)


@csrf_exempt
@api_view(["POST"])
@authentication_classes([JWTAuthentication])  # ✅ NUEVO
@permission_classes([IsAuthenticated])
def eventos_crear(request):
    """
    Espera JSON:
    {
      "titulo": str,
      "fecha": "YYYY-MM-DD",
      "descripcion": str,
      "school_course_id": int,  # referencia principal
      "curso": "ALL",           # sólo para crear un evento global en todos los cursos habilitados
      "tipo_evento": str
    }
    """
    if not _require_eventos_write_perm(request):
        return Response({"detail": "No autorizado."}, status=status.HTTP_403_FORBIDDEN)
    active_school = get_request_school(request)

    j = request.data or {}
    titulo = (j.get("titulo") or "").strip()
    fecha_str = (j.get("fecha") or "").strip()
    fecha = parse_date(fecha_str) if fecha_str else None
    descripcion = (j.get("descripcion") or "").strip()
    school_course, curso, course_error = resolve_course_reference(
        school=active_school,
        raw_course=j.get("curso"),
        raw_school_course_id=j.get("school_course_id"),
        required=True,
        allow_all_markers=True,
    )
    tipo_evento = (j.get("tipo_evento") or "").strip()

    if not titulo:
        return Response({"detail": "Título requerido."}, status=status.HTTP_400_BAD_REQUEST)
    if not fecha:
        return Response({"detail": "Fecha inválida o vacía."}, status=status.HTTP_400_BAD_REQUEST)
    if course_error:
        return Response({"detail": course_error}, status=status.HTTP_400_BAD_REQUEST)
    if not curso:
        return Response({"detail": "Curso requerido."}, status=status.HTTP_400_BAD_REQUEST)
    if not _is_all_cursos(curso) and school_course is None and not _is_valid_curso(curso, school=active_school):
        return Response({"detail": "Curso inválido."}, status=status.HTTP_400_BAD_REQUEST)

    # ✅ NUEVO: validar tipo_evento (si tu front manda cualquier cosa, lo frenamos prolijo)
    if not tipo_evento:
        return Response({"detail": "Tipo de evento requerido."}, status=status.HTTP_400_BAD_REQUEST)
    if not _is_valid_tipo_evento(tipo_evento):
        return Response({"detail": "Tipo de evento inválido."}, status=status.HTTP_400_BAD_REQUEST)

    if _has_role(request, "Preceptores") and not getattr(request.user, "is_superuser", False):
        # ✅ Preceptores pueden crear en cualquier curso y en "ALL"
        if _is_all_cursos(curso):
            preceptor_course_ids = _school_course_ids_habilitados_preceptor(request.user, school=active_school)
            cursos_all = list(
                SchoolCourse.objects.filter(
                    school=active_school,
                    is_active=True,
                    id__in=preceptor_course_ids,
                ).order_by("sort_order", "id")
            )
            if not cursos_all:
                return Response(
                    {"detail": "No tenÃ©s cursos asignados para crear eventos."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        elif not _preceptor_puede_ver_curso(
            request.user,
            curso,
            school=active_school,
            school_course=school_course,
        ):
            return Response(
                {"detail": "No tenÃ©s permiso para crear eventos en este curso."},
                status=status.HTTP_403_FORBIDDEN,
            )
    if _has_role(request, "Profesores") and not getattr(request.user, "is_superuser", False):
        if not _profesor_puede_ver_curso(
            request.user,
            curso,
            school=active_school,
            school_course=school_course,
        ):
            return Response(
                {"detail": "No tenés permiso para crear eventos en este curso."},
                status=status.HTTP_403_FORBIDDEN,
            )

    # ✅ "ALL" => crear un evento por cada curso disponible
    if _is_all_cursos(curso):
        if not (_has_role(request, "Preceptores") and not getattr(request.user, "is_superuser", False)):
            cursos_all = list(
                SchoolCourse.objects.filter(school=active_school, is_active=True).order_by("sort_order", "id")
            )
        if not cursos_all:
            return Response({"detail": "No hay cursos disponibles."}, status=status.HTTP_400_BAD_REQUEST)

        objs = [
            Evento(
                school=active_school,
                school_course=school_course,
                titulo=titulo,
                fecha=fecha,
                descripcion=descripcion,
                curso=school_course.code,
                tipo_evento=tipo_evento,
            )
            for school_course in cursos_all
        ]

        with transaction.atomic():
            created = Evento.objects.bulk_create(objs)

        # Notificamos uno por curso (puede ser pesado, pero requerido)
        for ev in created:
            _notify_evento_creado(request, ev)

        return Response({"creados": len(created)}, status=status.HTTP_201_CREATED)

    school_course = school_course or _resolve_school_course_for_event(curso, school=active_school)
    if school_course is None:
        return Response({"detail": "No existe ese curso en el colegio activo."}, status=status.HTTP_400_BAD_REQUEST)

    ev = Evento.objects.create(
        school=active_school,
        school_course=school_course,
        titulo=titulo,
        fecha=fecha,
        descripcion=descripcion,
        curso=getattr(school_course, "code", None) or curso,
        tipo_evento=tipo_evento,
    )

    _notify_evento_creado(request, ev)

    return Response(_serialize_evento(ev), status=status.HTTP_201_CREATED)


@csrf_exempt
@api_view(["POST", "PUT", "PATCH"])
@authentication_classes([JWTAuthentication])  # ✅ NUEVO
@permission_classes([IsAuthenticated])
def eventos_editar(request, pk: int):
    if not _require_eventos_write_perm(request):
        return Response({"detail": "No autorizado."}, status=status.HTTP_403_FORBIDDEN)
    active_school = get_request_school(request)

    ev = get_object_or_404(scope_queryset_to_school(Evento.objects.all(), active_school), pk=pk)

    if _has_role(request, "Preceptores") and not getattr(request.user, "is_superuser", False):
        # ✅ Preceptores pueden editar eventos de cualquier curso
        curso_actual = (getattr(getattr(ev, "school_course", None), "code", None) or getattr(ev, "curso", "") or "").strip()
        if curso_actual and not _preceptor_puede_ver_curso(
            request.user,
            curso_actual,
            school=active_school,
            school_course=getattr(ev, "school_course", None),
        ):
            return Response(
                {"detail": "No tenÃ©s permiso para editar eventos de este curso."},
                status=status.HTTP_403_FORBIDDEN,
            )
    if _has_role(request, "Profesores") and not getattr(request.user, "is_superuser", False):
        curso_actual = (getattr(getattr(ev, "school_course", None), "code", None) or getattr(ev, "curso", "") or "").strip()
        if curso_actual and not _profesor_puede_ver_curso(
            request.user,
            curso_actual,
            school=active_school,
            school_course=getattr(ev, "school_course", None),
        ):
            return Response(
                {"detail": "No tenés permiso para editar eventos de este curso."},
                status=status.HTTP_403_FORBIDDEN,
            )

    j = request.data or {}

    if "titulo" in j:
        ev.titulo = (j.get("titulo") or "").strip()

    if "fecha" in j:
        fecha_str = (j.get("fecha") or "").strip()
        fecha = parse_date(fecha_str) if fecha_str else None
        if fecha_str and not fecha:
            return Response({"detail": "Fecha inválida."}, status=status.HTTP_400_BAD_REQUEST)
        ev.fecha = fecha

    if "descripcion" in j:
        ev.descripcion = (j.get("descripcion") or "").strip()

    if "curso" in j or "school_course_id" in j:
        school_course_nuevo, curso_nuevo, course_error = resolve_course_reference(
            school=active_school,
            raw_course=j.get("curso"),
            raw_school_course_id=j.get("school_course_id"),
            required=True,
        )
        if course_error:
            return Response({"detail": course_error}, status=status.HTTP_400_BAD_REQUEST)
        if not curso_nuevo:
            return Response({"detail": "Curso requerido."}, status=status.HTTP_400_BAD_REQUEST)
        if school_course_nuevo is None and not _is_valid_curso(curso_nuevo, school=active_school):
            return Response({"detail": "Curso inválido."}, status=status.HTTP_400_BAD_REQUEST)

        if _has_role(request, "Preceptores") and not getattr(request.user, "is_superuser", False):
            # ✅ Preceptores pueden asignar cualquier curso
            if curso_nuevo and not _preceptor_puede_ver_curso(
                request.user,
                curso_nuevo,
                school=active_school,
                school_course=school_course_nuevo,
            ):
                return Response(
                    {"detail": "No tenÃ©s permiso para asignar este curso al evento."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        if _has_role(request, "Profesores") and not getattr(request.user, "is_superuser", False):
            if curso_nuevo and not _profesor_puede_ver_curso(
                request.user,
                curso_nuevo,
                school=active_school,
                school_course=school_course_nuevo,
            ):
                return Response(
                    {"detail": "No tenés permiso para asignar este curso al evento."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        school_course_nuevo = school_course_nuevo or _resolve_school_course_for_event(curso_nuevo, school=active_school)
        if school_course_nuevo is None:
            return Response({"detail": "No existe ese curso en el colegio activo."}, status=status.HTTP_400_BAD_REQUEST)
        ev.school_course = school_course_nuevo
        ev.curso = getattr(school_course_nuevo, "code", None) or curso_nuevo

    if "tipo_evento" in j:
        tipo = (j.get("tipo_evento") or "").strip()
        # ✅ NUEVO: validar tipo_evento al editar
        if tipo and not _is_valid_tipo_evento(tipo):
            return Response({"detail": "Tipo de evento inválido."}, status=status.HTTP_400_BAD_REQUEST)
        ev.tipo_evento = tipo

    ev.save()
    return Response(_serialize_evento(ev), status=status.HTTP_200_OK)


@csrf_exempt
@api_view(["POST", "DELETE"])
@authentication_classes([JWTAuthentication])  # ✅ NUEVO
@permission_classes([IsAuthenticated])
def eventos_eliminar(request, pk: int):
    if not _require_eventos_write_perm(request):
        return Response({"detail": "No autorizado."}, status=status.HTTP_403_FORBIDDEN)
    active_school = get_request_school(request)

    ev = get_object_or_404(scope_queryset_to_school(Evento.objects.all(), active_school), pk=pk)

    if _has_role(request, "Preceptores") and not getattr(request.user, "is_superuser", False):
        # ✅ Preceptores pueden eliminar eventos de cualquier curso
        curso_actual = (getattr(getattr(ev, "school_course", None), "code", None) or getattr(ev, "curso", "") or "").strip()
        if curso_actual and not _preceptor_puede_ver_curso(
            request.user,
            curso_actual,
            school=active_school,
            school_course=getattr(ev, "school_course", None),
        ):
            return Response(
                {"detail": "No tenÃ©s permiso para eliminar eventos de este curso."},
                status=status.HTTP_403_FORBIDDEN,
            )
    if _has_role(request, "Profesores") and not getattr(request.user, "is_superuser", False):
        curso_actual = (getattr(getattr(ev, "school_course", None), "code", None) or getattr(ev, "curso", "") or "").strip()
        if curso_actual and not _profesor_puede_ver_curso(
            request.user,
            curso_actual,
            school=active_school,
            school_course=getattr(ev, "school_course", None),
        ):
            return Response(
                {"detail": "No tenés permiso para eliminar eventos de este curso."},
                status=status.HTTP_403_FORBIDDEN,
            )

    ev.delete()
    return Response({"id": pk}, status=status.HTTP_200_OK)


@csrf_exempt
@api_view(["GET"])
@authentication_classes([JWTAuthentication])  # ✅ NUEVO
@permission_classes([IsAuthenticated])
def eventos_tipos(request):
    return Response(_tipos_evento_default(), status=status.HTTP_200_OK)


# ------------------------------------------------------------
# ✅ REST real (FRONT actual)
# ------------------------------------------------------------
@csrf_exempt
@api_view(["GET", "POST"])
@authentication_classes([JWTAuthentication])  # ✅ NUEVO
@permission_classes([IsAuthenticated])
def eventos_collection(request):
    """
    /eventos/
    - GET  -> eventos_listar
    - POST -> eventos_crear

    ✅ FIX: NO pasar DRF Request a otra vista @api_view.
    Hay que pasar el HttpRequest real (request._request).
    """
    raw = getattr(request, "_request", request)

    if request.method == "GET":
        return eventos_listar(raw)
    return eventos_crear(raw)


@csrf_exempt
@api_view(["POST", "PUT", "PATCH", "DELETE"])
@authentication_classes([JWTAuthentication])  # ✅ NUEVO
@permission_classes([IsAuthenticated])
def eventos_detalle(request, pk: int):
    """
    /eventos/<pk>/
    - PATCH/PUT/POST -> eventos_editar
    - DELETE         -> eventos_eliminar

    ✅ FIX: NO pasar DRF Request a otra vista @api_view.
    Hay que pasar el HttpRequest real (request._request).
    """
    raw = getattr(request, "_request", request)

    if request.method == "DELETE":
        return eventos_eliminar(raw, pk=pk)
    return eventos_editar(raw, pk=pk)


# ------------------------------------------------------------
# Cursos del preceptor (para selector de calendario)
# ------------------------------------------------------------
@csrf_exempt
@api_view(["GET"])
@authentication_classes([JWTAuthentication])  # ✅ NUEVO
@permission_classes([IsAuthenticated])
def preceptor_cursos(request):
    """
    Devuelve: {"cursos":[{"id":"5A","nombre":"5A"}, ...]}

    - Preceptor: devuelve sus cursos asignados en PreceptorCurso.
    - Superuser: también devuelve (si tiene asignaciones; si no, vacío).
    - Otros roles: devuelve vacío.
    """
    if not _has_role(request, "Preceptores") and not getattr(request.user, "is_superuser", False):
        return Response({"cursos": []}, status=status.HTTP_200_OK)
    active_school = get_request_school(request)

    if getattr(request.user, "is_superuser", False):
        cursos = sorted({str(code) for code, _name in get_school_course_choices(school=active_school)})
        return Response(_serialize_cursos_para_selector(cursos, school=active_school), status=status.HTTP_200_OK)

    if PreceptorCurso is None:
        return Response({"cursos": []}, status=status.HTTP_200_OK)

    try:
        cursos = _cursos_habilitados_preceptor(request.user, school=active_school)
    except Exception:
        cursos = []

    return Response(_serialize_cursos_para_selector(cursos, school=active_school), status=status.HTTP_200_OK)

