# calificaciones/api_eventos/_helpers.py
from django.utils.dateparse import parse_date
from django.contrib.auth import get_user_model

from ..contexto import resolve_alumno_for_user
from ..course_access import (
    build_course_membership_q,
    course_ref_matches,
    get_assignment_course_refs,
)
from ..models import Evento, Notificacion, SchoolCourse, resolve_school_course_for_value
from ..schools import scope_queryset_to_school
from ..user_groups import get_user_group_names
from ..utils_cursos import get_course_label, get_school_course_choices, is_curso_valido

# Intentamos importar Alumno para validar cursos y, si se puede, detectar curso del alumno
try:
    from ..models import Alumno  # type: ignore
except Exception:
    Alumno = None  # noqa: N816

User = get_user_model()

# ✅ PreceptorCurso para validar cursos asignados al preceptor
try:
    from ..models_preceptores import PreceptorCurso, ProfesorCurso  # type: ignore
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


def _crear_notificaciones_evento(*, ev: Evento, actor, curso: str, accion: str = "creado"):
    """Crea notificaciones de campana y email para un evento (curso completo)."""
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

    accion_labels = {
        "creado": "Nuevo evento en el calendario",
        "modificado": "Evento modificado en el calendario",
        "eliminado": "Evento eliminado del calendario",
    }
    accion_label = accion_labels.get(accion, "Evento en el calendario")
    titulo = f"{accion_label} ({course_name})"

    fecha = getattr(ev, "fecha", None)
    try:
        fecha_s = fecha.isoformat() if fecha else ""
    except Exception:
        fecha_s = str(fecha) if fecha else ""

    desc = (getattr(ev, "descripcion", None) or "").strip()
    tipo = (getattr(ev, "tipo_evento", None) or "").strip()
    actor_label = _user_label(actor) or (getattr(actor, "username", "") or "").strip()

    ev_titulo = (getattr(ev, "titulo", "") or "").strip()
    ev_desc_parts = []
    if ev_titulo:
        ev_desc_parts.append(ev_titulo)
    if fecha_s:
        ev_desc_parts.append(fecha_s)
    descripcion = " · ".join([p for p in ev_desc_parts if p]).strip()

    url = "/calendario"

    meta = {
        "evento_id": getattr(ev, "id", None),
        "school_course_id": getattr(ev, "school_course_id", None),
        "school_course_name": course_name,
        "fecha": fecha_s or None,
        "tipo_evento": tipo or None,
        "accion": accion,
        "actor": actor_label or None,
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
        created = len(notifs)
    except Exception:
        created = 0
        for n in notifs:
            try:
                n.save()
                created += 1
            except Exception:
                pass

    from django.conf import settings as _s
    if getattr(_s, "EMAIL_NOTIFICATIONS_ENABLED", True):
        for n in notifs:
            try:
                to_email = (getattr(n.destinatario, "email", "") or "").strip()
                if to_email:
                    from ..tasks import send_email_task
                    send_email_task.delay(
                        to_email=to_email,
                        subject=titulo,
                        text=descripcion,
                    )
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
    Entrada: iterable de códigos de curso.
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
    creado_por = _user_label(getattr(ev, "creado_por", None)) if getattr(ev, "creado_por_id", None) else ""

    return {
        "id": str(getattr(ev, "id", "")),
        "school_course_id": getattr(ev, "school_course_id", None),
        "school_course_name": curso_nombre,
        "title": getattr(ev, "titulo", "") or getattr(ev, "title", ""),
        "start": start,
        "creado_por": creado_por,
        "extendedProps": {
            "description": getattr(ev, "descripcion", "") or getattr(ev, "description", ""),
            "school_course_name": curso_nombre,
            "school_course_id": getattr(ev, "school_course_id", None),
            "tipo_evento": getattr(ev, "tipo_evento", ""),
            "creado_por": creado_por,
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
    try:
        curso = (getattr(ev, 'curso', '') or '').strip()
        actor = getattr(request, 'user', None)
        _crear_notificaciones_evento(ev=ev, actor=actor, curso=curso, accion="creado")
    except Exception:
        return


def _notify_evento_modificado(request, ev: Evento):
    try:
        curso = (getattr(ev, 'curso', '') or '').strip()
        actor = getattr(request, 'user', None)
        _crear_notificaciones_evento(ev=ev, actor=actor, curso=curso, accion="modificado")
    except Exception:
        return


def _notify_evento_eliminado(request, ev: Evento):
    try:
        curso = (getattr(ev, 'curso', '') or '').strip()
        actor = getattr(request, 'user', None)
        _crear_notificaciones_evento(ev=ev, actor=actor, curso=curso, accion="eliminado")
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
