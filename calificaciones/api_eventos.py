# calificaciones/api_eventos.py
from django.views.decorators.csrf import csrf_exempt
from django.utils.dateparse import parse_date
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework.decorators import (
    api_view,
    permission_classes,
    authentication_classes,  # ✅ NUEVO
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication  # ✅ NUEVO

from .models import Evento, Notificacion

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
    try:
        role = (request.GET.get("view_as") or request.headers.get("X-Preview-Role") or "").strip()
    except Exception:
        role = ""

    valid = {"Profesores", "Preceptores", "Padres", "Alumnos", "Directivos"}
    if role in valid and getattr(request.user, "is_superuser", False):
        return [role]

    try:
        return list(request.user.groups.values_list("name", flat=True))
    except Exception:
        return []


def _has_role(request, *roles):
    eff = set(_effective_groups(request))
    return any(r in eff for r in roles)


def _require_eventos_write_perm(request):
    # Solo roles que pueden crear/editar/eliminar eventos (y superuser)
    if getattr(request.user, "is_superuser", False):
        return True
    if _has_role(request, "Preceptores", "Profesores", "Directivos"):
        return True
    if getattr(request.user, "is_staff", False):
        return True
    return False


# ------------------------------------------------------------
# Notificaciones (campanita) para Eventos
# ------------------------------------------------------------
def _user_label(user) -> str:
    try:
        full = (user.get_full_name() or '').strip()
        if full:
            return full
        return (getattr(user, 'username', '') or '').strip()
    except Exception:
        return ''


def _add_destinatario(destinatarios, seen, u):
    try:
        if u is None:
            return
        uid = getattr(u, 'id', None)
        if uid is None or uid in seen:
            return
        seen.add(uid)
        destinatarios.append(u)
    except Exception:
        return


def _collect_destinatarios_evento(curso: str):
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

    qs = Alumno.objects.filter(curso=curso)  # type: ignore
    try:
        qs = qs.select_related('padre')
    except Exception:
        pass

    for a in qs:
        _add_destinatario(destinatarios, seen, getattr(a, 'padre', None))

        if 'usuario' in field_names:
            _add_destinatario(destinatarios, seen, getattr(a, 'usuario', None))

        # username==legajo/id_alumno
        try:
            legajo = (getattr(a, 'id_alumno', '') or '').strip()
            if legajo:
                _add_destinatario(destinatarios, seen, User.objects.filter(username__iexact=legajo).first())
        except Exception:
            pass

    return destinatarios


def _crear_notificaciones_evento(*, ev: Evento, actor, curso: str):
    """Crea notificaciones para un evento recién creado (curso completo)."""
    curso = (curso or "").strip()
    if not curso:
        return 0

    destinatarios = _collect_destinatarios_evento(curso)
    if not destinatarios:
        return 0

    titulo = f"Nuevo evento en el calendario ({curso})"

    fecha = getattr(ev, "fecha", None)
    try:
        fecha_s = fecha.isoformat() if fecha else ""
    except Exception:
        fecha_s = str(fecha) if fecha else ""

    desc = (getattr(ev, "descripcion", None) or "").strip()
    tipo = (getattr(ev, "tipo_evento", None) or "").strip()
    actor_label = _user_label(actor) or (getattr(actor, "username", "") or "").strip()

    lines = [f"Evento: {getattr(ev, 'titulo', '')}"]
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
        "curso": curso,
        "fecha": fecha_s or None,
        "tipo_evento": tipo or None,
        "creado_por": actor_label or None,
    }

    created = 0
    for u in destinatarios:
        try:
            Notificacion.objects.create(
                destinatario=u,
                tipo="evento",
                titulo=titulo,
                descripcion=descripcion,
                url=url,
                leida=False,
                meta=meta,
            )
            created += 1
        except Exception:
            pass

    return created


# ------------------------------------------------------------
# Validaciones / parsing
# ------------------------------------------------------------
def _parse_date(q):
    q = (q or "").strip()
    return parse_date(q) if q else None


def _is_valid_curso(curso: str) -> bool:
    """
    Valida contra Alumno.CURSOS si existe; si no, acepta cualquier string no vacío.
    """
    curso = (curso or "").strip()
    if not curso:
        return False

    if Alumno is None:
        return True

    try:
        cursos_validos = {c[0] for c in getattr(Alumno, "CURSOS", [])}
        if cursos_validos:
            return curso in cursos_validos
    except Exception:
        pass

    return True


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


def _curso_para_alumno_user(user):
    """
    Intenta deducir el curso del usuario alumno sin romper compatibilidad.
    Como tu modelo Alumno puede no tener campo usuario, esto prueba varios caminos.

    Si no puede, devuelve None.
    """
    if Alumno is None:
        return None

    try:
        field_names = {f.name for f in Alumno._meta.fields}  # type: ignore
    except Exception:
        field_names = set()

    def _try_filter(**kwargs):
        try:
            a = Alumno.objects.filter(**kwargs).first()  # type: ignore
            return getattr(a, "curso", None) if a else None
        except Exception:
            return None

    if "usuario" in field_names:
        curso = _try_filter(usuario=user)
        if curso:
            return curso

    if "user" in field_names:
        curso = _try_filter(user=user)
        if curso:
            return curso

    if "account" in field_names:
        curso = _try_filter(account=user)
        if curso:
            return curso

    try:
        a = getattr(user, "alumno", None)
        if a is not None:
            curso = getattr(a, "curso", None)
            if curso:
                return curso
    except Exception:
        pass

    if "id_alumno" in field_names:
        try:
            username = (getattr(user, "username", "") or "").strip()
            if username:
                curso = _try_filter(id_alumno=username)
                if curso:
                    return curso
        except Exception:
            pass

    return None


# ------------------------------------------------------------
# Permisos por curso para Preceptores
# ------------------------------------------------------------
def _cursos_habilitados_preceptor(user):
    """
    Devuelve lista de cursos habilitados para el preceptor.
    - Superuser: habilitado para todo.
    - Preceptor común: cursos asignados en PreceptorCurso.
    Si PreceptorCurso no está disponible, devuelve [] (modo seguro).
    """
    if getattr(user, "is_superuser", False):
        return ["*"]

    if PreceptorCurso is None:
        return []

    try:
        asignados = (
            PreceptorCurso.objects.filter(preceptor=user)
            .values_list("curso", flat=True)
            .distinct()
        )
        return sorted(set(asignados))
    except Exception:
        return []


def _preceptor_puede_ver_curso(user, curso: str) -> bool:
    curso = (curso or "").strip()
    if not curso:
        return False

    if getattr(user, "is_superuser", False):
        return True

    cursos = set(_cursos_habilitados_preceptor(user))
    return curso in cursos


def _cursos_habilitados_profesor(user):
    """
    Devuelve cursos asignados a profesor.
    - Superuser: habilitado para todo.
    - Si no hay asignaciones, devuelve [] (sin restricciones).
    """
    if getattr(user, "is_superuser", False):
        return ["*"]

    if ProfesorCurso is None:
        return []

    try:
        asignados = (
            ProfesorCurso.objects.filter(profesor=user)
            .values_list("curso", flat=True)
            .distinct()
        )
        return sorted(set(asignados))
    except Exception:
        return []


def _profesor_puede_ver_curso(user, curso: str) -> bool:
    curso = (curso or "").strip()
    if not curso:
        return False

    if getattr(user, "is_superuser", False):
        return True

    cursos = _cursos_habilitados_profesor(user)
    if not cursos:
        return True
    return curso in set(cursos)


# ------------------------------------------------------------
# Payload para selector del frontend
# ------------------------------------------------------------
def _serialize_cursos_para_selector(cursos):
    """
    Entrada: iterable de strings (cursos)
    Salida: {"cursos":[{"id":"5A","nombre":"5A"}, ...]}
    """
    out = []
    for c in cursos or []:
        c = (str(c) or "").strip()
        if not c:
            continue
        out.append({"id": c, "nombre": c})
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

    return {
        "id": str(getattr(ev, "id", "")),
        "title": getattr(ev, "titulo", "") or getattr(ev, "title", ""),
        "start": start,
        "extendedProps": {
            "description": getattr(ev, "descripcion", "") or getattr(ev, "description", ""),
            "curso": getattr(ev, "curso", ""),
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


def _collect_destinatarios_curso(curso: str):
    """Devuelve usuarios a notificar (alumnos + padres) para un curso."""
    if Alumno is None:
        return []

    curso = (curso or "").strip()
    if not curso:
        return []

    destinatarios = []
    seen = set()

    # Detectar si existe campo Alumno.usuario (algunos despliegues lo tienen)
    try:
        alumno_field_names = {f.name for f in Alumno._meta.fields}  # type: ignore
    except Exception:
        alumno_field_names = set()

    try:
        qs = Alumno.objects.filter(curso=curso).select_related("padre")  # type: ignore
    except Exception:
        qs = []

    for a in qs:
        # Padre
        _add_destinatario(destinatarios, seen, getattr(a, "padre", None))

        # Alumno explícito (si existe Alumno.usuario)
        if "usuario" in alumno_field_names:
            _add_destinatario(destinatarios, seen, getattr(a, "usuario", None))

        # Alumno por convención: username == legajo/id_alumno
        try:
            legajo = (getattr(a, "id_alumno", "") or "").strip()
            if legajo:
                u_alumno = User.objects.filter(username__iexact=legajo).first()
                _add_destinatario(destinatarios, seen, u_alumno)
        except Exception:
            pass

    return destinatarios


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
@csrf_exempt
@api_view(["GET"])
@authentication_classes([JWTAuthentication])  # ✅ NUEVO
@permission_classes([IsAuthenticated])
def eventos_listar(request):
    """
    Lista eventos.

    Query params:
    - curso=... (opcional según rol)
    - desde=YYYY-MM-DD (opcional)
    - hasta=YYYY-MM-DD (opcional)

    Reglas:
    - Alumnos: intenta usar su curso automáticamente. Si no se puede, exige curso=...
    - Preceptores: exige curso=... + valida que lo tenga asignado
    - Profesores/Directivos/Admin: curso opcional; si no lo pasan, trae todos
    """
    qs = Evento.objects.all()

    desde = _parse_date(request.GET.get("desde"))
    hasta = _parse_date(request.GET.get("hasta"))
    if desde:
        qs = qs.filter(fecha__gte=desde)
    if hasta:
        qs = qs.filter(fecha__lte=hasta)

    curso = (request.GET.get("curso") or "").strip()

    if _has_role(request, "Alumnos"):
        curso_auto = _curso_para_alumno_user(request.user)
        if curso_auto:
            curso = curso_auto
        elif not curso:
            return Response(
                {"detail": "Falta el parámetro 'curso' para alumnos (no se pudo detectar automáticamente)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    elif _has_role(request, "Preceptores"):
        if not curso:
            return Response(
                {"detail": "Falta el parámetro 'curso' para preceptores."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not _preceptor_puede_ver_curso(request.user, curso):
            return Response(
                {"detail": "No tenés permiso para ver eventos de este curso."},
                status=status.HTTP_403_FORBIDDEN,
            )
    elif _has_role(request, "Profesores"):
        cursos_prof = _cursos_habilitados_profesor(request.user)
        if curso:
            if cursos_prof and curso not in cursos_prof:
                return Response(
                    {"detail": "No tenés permiso para ver eventos de este curso."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        elif cursos_prof:
            qs = qs.filter(curso__in=cursos_prof)

    if curso:
        if not _is_valid_curso(curso):
            return Response({"detail": "Curso inválido."}, status=status.HTTP_400_BAD_REQUEST)
        qs = qs.filter(curso=curso)

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
      "curso": str,
      "tipo_evento": str
    }
    """
    if not _require_eventos_write_perm(request):
        return Response({"detail": "No autorizado."}, status=status.HTTP_403_FORBIDDEN)

    j = request.data or {}
    titulo = (j.get("titulo") or "").strip()
    fecha_str = (j.get("fecha") or "").strip()
    fecha = parse_date(fecha_str) if fecha_str else None
    descripcion = (j.get("descripcion") or "").strip()
    curso = (j.get("curso") or "").strip()
    tipo_evento = (j.get("tipo_evento") or "").strip()

    if not titulo:
        return Response({"detail": "Título requerido."}, status=status.HTTP_400_BAD_REQUEST)
    if not fecha:
        return Response({"detail": "Fecha inválida o vacía."}, status=status.HTTP_400_BAD_REQUEST)
    if not curso:
        return Response({"detail": "Curso requerido."}, status=status.HTTP_400_BAD_REQUEST)
    if not _is_valid_curso(curso):
        return Response({"detail": "Curso inválido."}, status=status.HTTP_400_BAD_REQUEST)

    # ✅ NUEVO: validar tipo_evento (si tu front manda cualquier cosa, lo frenamos prolijo)
    if not tipo_evento:
        return Response({"detail": "Tipo de evento requerido."}, status=status.HTTP_400_BAD_REQUEST)
    if not _is_valid_tipo_evento(tipo_evento):
        return Response({"detail": "Tipo de evento inválido."}, status=status.HTTP_400_BAD_REQUEST)

    if _has_role(request, "Preceptores") and not getattr(request.user, "is_superuser", False):
        if not _preceptor_puede_ver_curso(request.user, curso):
            return Response(
                {"detail": "No tenés permiso para crear eventos en este curso."},
                status=status.HTTP_403_FORBIDDEN,
            )
    if _has_role(request, "Profesores") and not getattr(request.user, "is_superuser", False):
        if not _profesor_puede_ver_curso(request.user, curso):
            return Response(
                {"detail": "No tenés permiso para crear eventos en este curso."},
                status=status.HTTP_403_FORBIDDEN,
            )

    ev = Evento.objects.create(
        titulo=titulo,
        fecha=fecha,
        descripcion=descripcion,
        curso=curso,
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

    ev = get_object_or_404(Evento, pk=pk)

    if _has_role(request, "Preceptores") and not getattr(request.user, "is_superuser", False):
        curso_actual = (getattr(ev, "curso", "") or "").strip()
        if curso_actual and not _preceptor_puede_ver_curso(request.user, curso_actual):
            return Response(
                {"detail": "No tenés permiso para editar eventos de este curso."},
                status=status.HTTP_403_FORBIDDEN,
            )
    if _has_role(request, "Profesores") and not getattr(request.user, "is_superuser", False):
        curso_actual = (getattr(ev, "curso", "") or "").strip()
        if curso_actual and not _profesor_puede_ver_curso(request.user, curso_actual):
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

    if "curso" in j:
        curso_nuevo = (j.get("curso") or "").strip()
        if curso_nuevo and not _is_valid_curso(curso_nuevo):
            return Response({"detail": "Curso inválido."}, status=status.HTTP_400_BAD_REQUEST)

        if _has_role(request, "Preceptores") and not getattr(request.user, "is_superuser", False):
            if curso_nuevo and not _preceptor_puede_ver_curso(request.user, curso_nuevo):
                return Response(
                    {"detail": "No tenés permiso para asignar este curso al evento."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        if _has_role(request, "Profesores") and not getattr(request.user, "is_superuser", False):
            if curso_nuevo and not _profesor_puede_ver_curso(request.user, curso_nuevo):
                return Response(
                    {"detail": "No tenés permiso para asignar este curso al evento."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        ev.curso = curso_nuevo

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

    ev = get_object_or_404(Evento, pk=pk)

    if _has_role(request, "Preceptores") and not getattr(request.user, "is_superuser", False):
        curso_actual = (getattr(ev, "curso", "") or "").strip()
        if curso_actual and not _preceptor_puede_ver_curso(request.user, curso_actual):
            return Response(
                {"detail": "No tenés permiso para eliminar eventos de este curso."},
                status=status.HTTP_403_FORBIDDEN,
            )
    if _has_role(request, "Profesores") and not getattr(request.user, "is_superuser", False):
        curso_actual = (getattr(ev, "curso", "") or "").strip()
        if curso_actual and not _profesor_puede_ver_curso(request.user, curso_actual):
            return Response(
                {"detail": "No tenés permiso para eliminar eventos de este curso."},
                status=status.HTTP_403_FORBIDDEN,
            )

    ev.delete()
    return Response({"ok": True}, status=status.HTTP_200_OK)


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
# Curso del alumno (para calendario filtrado)
# ------------------------------------------------------------
@csrf_exempt
@api_view(["GET"])
@authentication_classes([JWTAuthentication])  # ✅ NUEVO
@permission_classes([IsAuthenticated])
def mi_curso(request):
    """
    Devuelve: {"curso": "<CURSO>"} para el usuario alumno.
    Si no encuentra curso, devuelve {"curso": ""}.
    """
    if Alumno is None:
        return Response({"curso": ""}, status=status.HTTP_200_OK)

    try:
        groups = list(request.user.groups.values_list("name", flat=True))
    except Exception:
        groups = []

    if "Alumnos" not in groups and not getattr(request.user, "is_superuser", False):
        return Response({"curso": ""}, status=status.HTTP_200_OK)

    curso = _curso_para_alumno_user(request.user)
    curso = (curso or "").strip()
    return Response({"curso": curso}, status=status.HTTP_200_OK)


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

    if PreceptorCurso is None:
        return Response({"cursos": []}, status=status.HTTP_200_OK)

    try:
        asignados = (
            PreceptorCurso.objects.filter(preceptor=request.user)
            .values_list("curso", flat=True)
            .distinct()
        )
        cursos = sorted(set(asignados))
    except Exception:
        cursos = []

    return Response(_serialize_cursos_para_selector(cursos), status=status.HTTP_200_OK)
