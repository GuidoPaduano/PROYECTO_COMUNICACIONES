# calificaciones/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import ValidationError
from django import forms

from datetime import date
from django.utils.dateparse import parse_date
from django.utils import timezone

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
from rest_framework.decorators import (
    action, api_view, authentication_classes, permission_classes, parser_classes, throttle_classes
)
from rest_framework.throttling import UserRateThrottle
from django.utils.decorators import method_decorator

from reportlab.pdfgen import canvas

from django.db.models import Q  # ✅ NUEVO (para filtros robustos de no leídos)

from .models import Alumno, Nota, Mensaje, Evento, Asistencia, Notificacion
from .utils_cursos import filtrar_cursos_validos
from .serializers import EventoSerializer, AlumnoFullSerializer, NotaPublicSerializer  # ⬅️ NUEVO
from .constants import MATERIAS
from .contexto import resolve_alumno_for_user
from django.contrib.auth import logout as dj_logout, update_session_auth_hash
from django.contrib.auth import get_user_model

import json
import logging

logger = logging.getLogger(__name__)

try:
    # ✅ NUEVO: si existen los modelos reales preceptor/profesor→cursos, los usamos para permisos
    from .models_preceptores import PreceptorCurso, ProfesorCurso  # type: ignore
except Exception:
    PreceptorCurso = None
    ProfesorCurso = None


# =========================================================
#  Notificaciones por NOTA (campanita: Notificacion del sistema)
# =========================================================

def _infer_tipo_remitente_local(user) -> str:
    """Devuelve un tipo válido para Mensaje.tipo_remitente."""
    try:
        if user.groups.filter(name__icontains="precep").exists():
            return "Preceptor"
        if user.groups.filter(name__icontains="direct").exists():
            return "Directivo"
        if user.groups.filter(name__icontains="profe").exists():
            return "Profesor"
    except Exception:
        pass
    return "Profesor"


def _resolver_destinatario_padre(alumno):
    """Destinatario para notificación.

    Preferencia: Alumno.padre (FK real)
    Fallback legacy: User.username == alumno.id_alumno
    """
    padre = getattr(alumno, "padre", None)
    if padre:
        return padre, "alumno.padre"

    try:
        User = get_user_model()
        legajo = (getattr(alumno, "id_alumno", "") or "").strip()
        if not legajo:
            return None, None
        u = User.objects.filter(username__iexact=legajo).first()
        if u:
            return u, "username==id_alumno"
    except Exception:
        return None, None

    return None, None


def _resolver_destinatarios_notif(alumno):
    """Destinatarios para notificaciones (campanita) relacionadas al alumno.

    - Padre asignado (alumno.padre) si existe
    - Alumno.usuario si existe
    - Fallback: User.username == alumno.id_alumno (legajo)

    (sin duplicados)
    """
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

    # Padre
    _add(getattr(alumno, "padre", None))

    # Alumno (vínculo explícito)
    _add(getattr(alumno, "usuario", None))

    # Alumno por convención username==legajo
    try:
        User = get_user_model()
        legajo = (getattr(alumno, "id_alumno", "") or "").strip()
        if legajo:
            _add(User.objects.filter(username__iexact=legajo).first())
    except Exception:
        pass

    # Último fallback: el resolver legacy de padre
    if not destinatarios:
        try:
            u_fb, _src = _resolver_destinatario_padre(alumno)
            _add(u_fb)
        except Exception:
            pass

    return destinatarios


def _notify_padre_por_nota(remitente, nota, *, silent=True):
    """Crea una Notificacion del sistema (campanita) al padre/tutor del alumno informando una NOTA.

    Importante:
    - NO crea un Mensaje (bandeja de entrada).
    - La bandeja queda solo para mensajería real entre usuarios.
    """
    try:
        alumno = getattr(nota, "alumno", None)
        if not alumno:
            return False

        destinatarios = _resolver_destinatarios_notif(alumno)
        if not destinatarios:
            return False

        # Nombre consistente (el modelo Alumno del proyecto no tiene 'apellido', pero dejamos fallback por si aparece)
        nombre = (f"{getattr(alumno, 'apellido', '')}, {getattr(alumno, 'nombre', '')}").strip(", ").strip()
        if not nombre:
            nombre = (getattr(alumno, "nombre", "") or "").strip() or str(getattr(alumno, "id_alumno", ""))

        curso = (getattr(alumno, "curso", "") or "").strip()
        materia = (getattr(nota, "materia", "") or "").strip()
        tipo = (getattr(nota, "tipo", "") or "").strip()
        calif = (getattr(nota, "calificacion", "") or "").strip()
        cuatri = getattr(nota, "cuatrimestre", None)
        fecha = getattr(nota, "fecha", None)
        obs = (getattr(nota, "observaciones", "") or "").strip()

        titulo = f"Nueva nota para {nombre}"

        # Descripción compacta (no hace falta que parezca un email)
        parts = []
        parts.append("Se registró una nueva calificación.")
        if curso:
            parts.append(f"Curso: {curso}")
        if materia:
            parts.append(f"Materia: {materia}")
        if tipo:
            parts.append(f"Tipo: {tipo}")
        if calif:
            parts.append(f"Calificación: {calif}")
        if cuatri:
            parts.append(f"Cuatrimestre: {cuatri}")
        if hasattr(fecha, "isoformat"):
            parts.append(f"Fecha: {fecha.isoformat()}")
        if obs:
            parts.append(f"Obs: {obs}")

        descripcion = " · ".join([p for p in parts if p]).strip()

        # URL destino (Parte B/C usan esto)
        url = f"/alumnos/{alumno.id}/?tab=notas"

        for destinatario in destinatarios:
            Notificacion.objects.create(
                destinatario=destinatario,
                tipo="nota",
                titulo=titulo,
                descripcion=descripcion,
                url=url,
                meta={
                    "alumno_id": alumno.id,
                    "nota_id": getattr(nota, "id", None),
                    "curso": curso or None,
                },
                leida=False,
            )
        return True
    except Exception:
        if silent:
            return False
        raise


def _notify_padres_por_notas_bulk(remitente, notas, *, silent=True):
    """Notificación optimizada: 1 Notificacion por ALUMNO (campanita), sin ensuciar bandeja.

    Devuelve cantidad de notificaciones creadas.
    """
    try:
        if not notas:
            return 0

        grupos = {}
        for n in notas:
            alumno = getattr(n, "alumno", None)
            if not alumno:
                continue

            # ✅ Igual que en la API: notificamos a PADRE y ALUMNO (si existe vínculo)
            destinatarios = _resolver_destinatarios_notif(alumno)
            if not destinatarios:
                continue

            for destinatario in destinatarios:
                key = (getattr(destinatario, "id", None), getattr(alumno, "id", None))
                if key not in grupos:
                    nombre = (f"{getattr(alumno, 'apellido', '')}, {getattr(alumno, 'nombre', '')}").strip(", ").strip()
                    if not nombre:
                        nombre = (getattr(alumno, "nombre", "") or "").strip() or str(getattr(alumno, "id_alumno", ""))

                    grupos[key] = {
                        "dest": destinatario,
                        "alumno": alumno,
                        "nombre": nombre,
                        "curso": (getattr(alumno, "curso", "") or "").strip(),
                        "notas": [],
                    }

                grupos[key]["notas"].append(n)

        if not grupos:
            return 0

        notifs = []

        for g in grupos.values():
            alumno = g["alumno"]
            nombre = g["nombre"]
            curso = g["curso"]
            notas_alumno = g["notas"]

            titulo = f"Nueva nota para {nombre}" if len(notas_alumno) == 1 else f"Nuevas notas para {nombre}"

            # Orden lindo
            try:
                notas_alumno = sorted(
                    notas_alumno,
                    key=lambda x: (
                        getattr(x, "fecha", None) or timezone.localdate(),
                        getattr(x, "materia", ""),
                    ),
                )
            except Exception:
                pass

            lines = []
            for nn in notas_alumno:
                materia = (getattr(nn, "materia", "") or "").strip()
                tipo = (getattr(nn, "tipo", "") or "").strip()
                calif = (getattr(nn, "calificacion", "") or "").strip()
                fecha = getattr(nn, "fecha", None)
                fstr = fecha.isoformat() if hasattr(fecha, "isoformat") else ""

                base = f"• {materia} ({tipo}): {calif}".strip()
                if fstr:
                    base += f" — {fstr}"
                lines.append(base)

            descripcion = "Se registraron nuevas calificaciones."
            if curso:
                descripcion += f" Curso: {curso}."
            if lines:
                # Guardamos en texto (la UI lo truncará si hace falta)
                descripcion += " " + " ".join(lines)

            url = f"/alumnos/{alumno.id}/?tab=notas"

            notifs.append(
                Notificacion(
                    destinatario=g["dest"],
                    tipo="nota",
                    titulo=titulo,
                    descripcion=descripcion,
                    url=url,
                    meta={
                        "alumno_id": alumno.id,
                        "nota_ids": [getattr(x, "id", None) for x in notas_alumno],
                        "curso": curso or None,
                    },
                    leida=False,
                )
            )

        if notifs:
            Notificacion.objects.bulk_create(notifs)

        return len(notifs)
    except Exception:
        if silent:
            return 0
        raise



# ============================================================
# Helper: Vista previa de rol (“Vista como…”) para superusuario
# ============================================================
def _get_preview_role(request):
    """
    Devuelve un rol de vista previa si el usuario es superusuario y pidió simular un rol.
    Lee `view_as` (querystring) o el header `X-Preview-Role`.
    Valores válidos: 'Profesores', 'Preceptores', 'Padres', 'Alumnos'.
    """
    try:
        role = (request.GET.get("view_as") or request.headers.get("X-Preview-Role") or "").strip()
    except Exception:
        role = ""
    valid = {"Profesores", "Preceptores", "Padres", "Alumnos"}
    if role in valid and getattr(request.user, "is_superuser", False):
        return role
    return None


# =========================================================
#  Formularios
# =========================================================
class EventoForm(forms.ModelForm):
    class Meta:
        model = Evento
        fields = ['titulo', 'descripcion', 'fecha', 'curso', 'tipo_evento']
        widgets = {
            'fecha': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }


# =========================================================
#  Helpers
# =========================================================
def _coerce_json(request):
    """Intenta parsear JSON manualmente si request.data viene vacío."""
    if getattr(request, "data", None):
        return request.data
    try:
        raw = (request.body or b"").decode("utf-8")
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _normalize_event_payload(payload):
    """
    Acepta claves alternativas desde el front:
      - titulo|title
      - descripcion|description
      - fecha|date
      - curso|course
      - tipo_evento|tipo|type
    """
    def first(*keys):
        for k in keys:
            if k in payload:
                return payload.get(k)
        return None

    return {
        "titulo":      first("titulo", "title") or "",
        "descripcion": first("descripcion", "description") or "",
        "fecha":       first("fecha", "date"),
        "curso":       first("curso", "course") or "",
        "tipo_evento": first("tipo_evento", "tipo", "type") or "",
    }


def obtener_curso_del_preceptor(usuario):
    # Mapeo simple para pruebas. Cambialo cuando tengas el modelo real de preceptores.
    cursos_por_usuario = {
        'preceptor1': '1A',
        'preceptor2': '3B',
        'preceptor3': '5NAT',
    }
    return cursos_por_usuario.get(usuario.username, None)


def _rol_principal(user):
    if getattr(user, "is_superuser", False):
        return "superusuario"
    for g in ("Profesores", "Padres", "Alumnos", "Preceptores"):
        if user.groups.filter(name=g).exists():
            return g
    return "—"


def _alumno_to_dict(a: Alumno):
    if not a:
        return None
    return {
        "id": a.id,
        "id_alumno": getattr(a, "id_alumno", None),
        "nombre": a.nombre,
        "curso": a.curso,
        "padre_id": a.padre_id,
        "usuario_id": getattr(a, "usuario_id", None),
    }


# ===== Helpers de rol efectivos (aplican vista previa) =====
def _effective_groups(request):
    pr = _get_preview_role(request)
    if pr and getattr(request.user, "is_superuser", False):
        return [pr]
    try:
        return list(request.user.groups.values_list("name", flat=True))
    except Exception:
        return []


def _has_role(request, *roles):
    eff = set(_effective_groups(request))
    return any(r in eff for r in roles)


# ===== Helper: detectar si un campo existe en el modelo (para contadores) =====
def _has_model_field(model, name: str) -> bool:
    try:
        model._meta.get_field(name)
        return True
    except Exception:
        return False


# =========================================================
#  ✅ NUEVO: permisos de PRECEPTOR por curso (PreceptorCurso o fallback)
# =========================================================
def _preceptor_can_access_alumno(user, alumno: Alumno) -> bool:
    """
    Permite acceso a preceptor SOLO si el alumno pertenece a un curso asignado a ese preceptor.

    - Si existe PreceptorCurso, se consulta ahí.
    - Si NO existe, se usa el helper obtener_curso_del_preceptor() como fallback.
    """
    curso_alumno = getattr(alumno, "curso", None)
    if not curso_alumno:
        return False

    if PreceptorCurso is not None:
        # Intento "directo" por convención habitual
        try:
            if PreceptorCurso.objects.filter(preceptor=user, curso=curso_alumno).exists():
                return True
        except Exception:
            pass

        # Intentos robustos por si cambian nombres de campos
        possible_user_fields = ["preceptor", "usuario", "user"]
        possible_curso_fields = ["curso", "curso_id", "curso_codigo", "curso_nombre"]
        for uf in possible_user_fields:
            for cf in possible_curso_fields:
                try:
                    if PreceptorCurso.objects.filter(**{uf: user, cf: curso_alumno}).exists():
                        return True
                except Exception:
                    continue

        return False

    # Fallback (tu mapeo hardcodeado)
    return obtener_curso_del_preceptor(user) == curso_alumno


def _profesor_cursos_asignados(user):
    if ProfesorCurso is None:
        return []
    try:
        return list(
            ProfesorCurso.objects.filter(profesor=user)
            .values_list("curso", flat=True)
            .distinct()
        )
    except Exception:
        return []


def _profesor_can_access_curso(user, curso: str) -> bool:
    curso = (curso or "").strip()
    if not curso:
        return False

    asignados = _profesor_cursos_asignados(user)
    if not asignados:
        return True
    return curso in set(asignados)


def _profesor_can_access_alumno(user, alumno: Alumno) -> bool:
    curso_alumno = getattr(alumno, "curso", None)
    if not curso_alumno:
        return False
    return _profesor_can_access_curso(user, curso_alumno)


# =========================================================
#  ✅ NUEVO: Compat Mensaje (emisor/receptor vs remitente/destinatario)
# =========================================================
def _mensaje_sender_field() -> str:
    return "remitente" if _has_model_field(Mensaje, "remitente") else "emisor"


def _mensaje_recipient_field() -> str:
    return "destinatario" if _has_model_field(Mensaje, "destinatario") else "receptor"


def _mensaje_curso_field() -> str:
    if _has_model_field(Mensaje, "curso_asociado"):
        return "curso_asociado"
    if _has_model_field(Mensaje, "curso"):
        return "curso"
    return ""


def _mensajes_inbox_qs(user):
    rf = _mensaje_recipient_field()
    return Mensaje.objects.filter(**{rf: user})


def _mensajes_sent_qs(user):
    sf = _mensaje_sender_field()
    return Mensaje.objects.filter(**{sf: user})


# =========================================================
#  Vistas HTML / Index
# =========================================================
@login_required
def index(request):
    # Usa roles efectivos (respetan vista previa)
    if _has_role(request, 'Padres'):
        return render(request, 'calificaciones/index.html')
    elif _has_role(request, 'Profesores') or request.user.is_superuser:
        return render(request, 'calificaciones/index.html')
    else:
        return HttpResponse("No tienes permiso.", status=403)


# =========================================================
#  PERFIL API (GET+PATCH) para Next.js — JWT o sesión
# =========================================================
@csrf_exempt
@api_view(["GET", "PATCH"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def perfil_api(request):
    """
    - GET: datos del usuario + contexto (alumno propio, hijos, preceptor, contadores)
    - PATCH: actualiza first_name, last_name, email del usuario autenticado.
    """
    user = request.user

    # ===== Vista previa de rol (“Vista como…”) para superusuario =====
    try:
        preview_role = _get_preview_role(request)
    except Exception:
        preview_role = None

    # Grupos efectivos
    grupos_reales = list(user.groups.values_list('name', flat=True))
    grupos = [preview_role] if preview_role else grupos_reales

    # Rol real + rol efectivo para UI
    try:
        rol_real = _rol_principal(user)
    except Exception:
        rol_real = grupos_reales[0] if grupos_reales else "—"
    rol = preview_role if preview_role else rol_real

    # ===== Contextos =====
    alumno_propio = None
    alumnos_del_padre = []
    curso_preceptor = None

    alumno_resolution = None

    # Alumno (robusto/retrocompatible)
    if "Alumnos" in grupos:
        r = resolve_alumno_for_user(user)
        alumno_resolution = {"method": r.method, "candidates": r.candidates}

        if r.alumno:
            alumno_propio = _alumno_to_dict(r.alumno)
        else:
            # Fallback para vista previa: tomar cualquier alumno
            if preview_role:
                a0 = Alumno.objects.order_by('id').first()
                alumno_propio = _alumno_to_dict(a0) if a0 else None

    # Padre
    if "Padres" in grupos:
        try:
            hijos = Alumno.objects.filter(padre=user).order_by('curso', 'nombre')
            alumnos_del_padre = [_alumno_to_dict(x) for x in hijos]
        except Exception:
            alumnos_del_padre = []
        # Fallback vista previa: elegir un padre real y listar sus hijos
        if preview_role and not alumnos_del_padre:
            a0 = Alumno.objects.filter(padre__isnull=False).order_by('padre_id').first()
            if a0 and a0.padre_id:
                hijos = Alumno.objects.filter(padre_id=a0.padre_id).order_by('curso', 'nombre')
                alumnos_del_padre = [_alumno_to_dict(x) for x in hijos]

    # Preceptor
    if "Preceptores" in grupos:
        try:
            a0 = Alumno.objects.order_by('curso').first()
            if a0 and a0.curso:
                curso_preceptor = a0.curso
            elif getattr(Alumno, "CURSOS", None):
                curso_preceptor = Alumno.CURSOS[0][0]
            else:
                curso_preceptor = None
        except Exception:
            curso_preceptor = None

    # ===== PATCH =====
    if request.method == "PATCH":
        payload = _coerce_json(request)
        first_name = (payload.get("first_name") or "").strip()
        last_name = (payload.get("last_name") or "").strip()
        email = (payload.get("email") or "").strip()

        changed = False
        if first_name or first_name == "":
            user.first_name = first_name
            changed = True
        if last_name or last_name == "":
            user.last_name = last_name
            changed = True
        if email:
            # Evitar emails duplicados
            try:
                User = get_user_model()
                if User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
                    return JsonResponse({"detail": "Ese correo ya está en uso."}, status=400)
            except Exception:
                pass
            user.email = email
            changed = True

        if changed:
            try:
                user.full_clean(exclude=['password'])
            except Exception:
                return JsonResponse({"detail": "Datos inválidos"}, status=400)
            user.save()

    # ===== Stats =====
    if "Alumnos" in grupos and alumno_propio:
        notas_count = Nota.objects.filter(alumno_id=alumno_propio["id"]).count()
    elif "Padres" in grupos and alumnos_del_padre:
        notas_count = Nota.objects.filter(alumno_id__in=[a["id"] for a in alumnos_del_padre]).count()
    else:
        notas_count = 0

    # ✅ FIX: Mensajes (compat emisor/receptor vs remitente/destinatario)
    inbox_qs = _mensajes_inbox_qs(user)
    sent_qs = _mensajes_sent_qs(user)

    mensajes_recibidos = inbox_qs.count()
    mensajes_enviados = sent_qs.count()

    # cálculo defensivo de "no leídos" (según campos existentes en tu modelo)
    if _has_model_field(Mensaje, "leido") and _has_model_field(Mensaje, "leido_en"):
        mensajes_no_leidos = inbox_qs.filter(Q(leido=False) | Q(leido_en__isnull=True)).count()
    elif _has_model_field(Mensaje, "leido"):
        mensajes_no_leidos = inbox_qs.filter(leido=False).count()
    elif _has_model_field(Mensaje, "leido_en"):
        mensajes_no_leidos = inbox_qs.filter(leido_en__isnull=True).count()
    elif _has_model_field(Mensaje, "fecha_lectura"):
        mensajes_no_leidos = inbox_qs.filter(fecha_lectura__isnull=True).count()
    else:
        mensajes_no_leidos = 0

    data = {
        "user": {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "is_superuser": user.is_superuser,
            "grupos": grupos,   # efectivos
            "rol": rol,         # efectivo
        },
        "alumno": alumno_propio,
        "alumno_resolution": alumno_resolution,
        "alumnos_del_padre": alumnos_del_padre,
        "curso_preceptor": curso_preceptor,
        "stats": {
            "notas_count": notas_count,
            "mensajes_recibidos": mensajes_recibidos,
            "mensajes_no_leidos": mensajes_no_leidos,
            "mensajes_enviados": mensajes_enviados,
        },
    }
    return JsonResponse(data)


# =========================================================
#  ✅ FIX NUEVO: endpoint que tu front espera para calendario
#      GET /api/mi-curso/  ->  { "curso": "1A" }
# =========================================================
@csrf_exempt
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mi_curso(request):
    """
    Devuelve el curso asociado al usuario logueado.

    Casos:
    - Alumno: curso del alumno vinculado (resolve_alumno_for_user)
    - Padre: curso del hijo (primero), o seleccionar por ?id_alumno=... o ?alumno_id=...
    - Preceptor: curso asignado por obtener_curso_del_preceptor
    - Superuser: si está en vista previa, se comporta como ese rol; si no, devuelve ?curso=... o el primer curso disponible
    """
    user = request.user
    preview_role = _get_preview_role(request)
    grupos = [preview_role] if (preview_role and user.is_superuser) else list(user.groups.values_list("name", flat=True))

    curso = None

    # 1) Alumno
    if "Alumnos" in grupos:
        r = resolve_alumno_for_user(user)
        if r.alumno:
            curso = getattr(r.alumno, "curso", None)
        elif preview_role and user.is_superuser:
            a0 = Alumno.objects.order_by("curso", "id").first()
            curso = getattr(a0, "curso", None) if a0 else None

    # 2) Padre
    if curso is None and "Padres" in grupos:
        alumno_pk = (request.GET.get("alumno_id") or "").strip()
        legajo = (request.GET.get("id_alumno") or "").strip()

        alumno = None
        if alumno_pk.isdigit():
            try:
                alumno = Alumno.objects.get(pk=int(alumno_pk), padre=user) if not preview_role else Alumno.objects.get(pk=int(alumno_pk))
            except Exception:
                alumno = None
        elif legajo:
            try:
                alumno = Alumno.objects.get(id_alumno=str(legajo), padre=user) if not preview_role else Alumno.objects.get(id_alumno=str(legajo))
            except Exception:
                alumno = None

        if alumno is None:
            qs = Alumno.objects.filter(padre=user).order_by("curso", "nombre")
            if not qs.exists() and preview_role and user.is_superuser:
                a0 = Alumno.objects.filter(padre__isnull=False).order_by("padre_id", "curso").first()
                if a0 and a0.padre_id:
                    qs = Alumno.objects.filter(padre_id=a0.padre_id).order_by("curso", "nombre")
            alumno = qs.first() if qs is not None else None

        curso = getattr(alumno, "curso", None) if alumno else None

    # 3) Preceptor
    if curso is None and "Preceptores" in grupos:
        curso = obtener_curso_del_preceptor(user)
        if (curso is None) and preview_role and user.is_superuser:
            a0 = Alumno.objects.order_by("curso", "id").first()
            curso = getattr(a0, "curso", None) if a0 else None

    # 4) Superuser sin vista previa: permitir querystring o fallback
    if curso is None and user.is_superuser and not preview_role:
        curso_qs = (request.GET.get("curso") or "").strip()
        if curso_qs:
            curso = curso_qs
        else:
            try:
                curso = Alumno.CURSOS[0][0] if getattr(Alumno, "CURSOS", None) else None
            except Exception:
                curso = None

    if not curso:
        return Response({"detail": "No se pudo resolver el curso para este usuario.", "curso": None}, status=200)

    return Response({"curso": curso}, status=200)


# =========================================================
#  Catálogos/Alumnos para "Nueva nota"
# =========================================================
@csrf_exempt
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def notas_catalogos(request):
    """
    Devuelve catálogos base para la pantalla de "Nueva nota".
    - cursos: lista id/nombre sacada de Alumno.CURSOS
    - materias: lista desde constants.MATERIAS
    - tipos: (opcional) vacío por ahora; se puede poblar luego si definen choices
    """
    cursos_base = filtrar_cursos_validos(getattr(Alumno, "CURSOS", []))
    cursos = [{"id": c[0], "nombre": c[1]} for c in cursos_base]
    if _has_role(request, "Profesores") and not request.user.is_superuser:
        asignados = _profesor_cursos_asignados(request.user)
        if asignados:
            asignados_set = set(asignados)
            cursos = [c for c in cursos if c.get("id") in asignados_set]
    materias = list(MATERIAS)
    tipos = []  # futuro: mapear choices de Nota si existen

    return Response({
        "cursos": cursos,
        "materias": materias,
        "tipos": tipos,
    })


# =========================================================
#  ✅ NUEVO: API cursos del preceptor (para selects del front)
# =========================================================
@csrf_exempt
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def preceptor_cursos(request):
    """
    GET /preceptor/cursos/
    - Superusuario: devuelve todos los cursos definidos en Alumno.CURSOS
    - Preceptor: devuelve sólo su curso (según helper obtener_curso_del_preceptor)
    """
    user = request.user
    if user.is_superuser:
        cursos_base = filtrar_cursos_validos(getattr(Alumno, "CURSOS", []))
        cursos = [{"id": c[0], "nombre": c[1]} for c in cursos_base]
    elif _has_role(request, 'Preceptores'):
        cid = obtener_curso_del_preceptor(user)
        nombre = dict(getattr(Alumno, "CURSOS", [])).get(cid, cid)
        cursos = [{"id": cid, "nombre": nombre}] if cid else []
    else:
        cursos = []
    return Response(cursos)


def _build_alumnos_payload(qs):
    """
    Helper interno: arma el JSON de alumnos para UI.
    (Se usa tanto para querystring como para ruta /curso/<id>/)
    """
    data = []
    for a in qs:
        p = getattr(a, "padre", None)
        padre_nombre = ""
        if p:
            try:
                padre_nombre = (p.get_full_name() or p.username or p.email or "").strip()
            except Exception:
                padre_nombre = getattr(p, "username", "") or getattr(p, "email", "") or ""

        data.append({
            "id": a.id,
            "id_alumno": getattr(a, "id_alumno", None),
            "nombre": a.nombre,
            "apellido": getattr(a, "apellido", "") if _has_model_field(Alumno, "apellido") else "",
            "curso": a.curso,
            "padre": {
                "id": getattr(p, "id", None) if p else None,
                "username": getattr(p, "username", "") if p else "",
                "first_name": getattr(p, "first_name", "") if p else "",
                "last_name": getattr(p, "last_name", "") if p else "",
                "email": getattr(p, "email", "") if p else "",
                "nombre_completo": padre_nombre,
            }
        })
    return {"alumnos": data}


@csrf_exempt
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def alumnos_por_curso(request):
    """
    GET /api/alumnos/?curso=ID
    Devuelve alumnos de un curso, incluyendo datos del padre/tutor para UI.
    """
    curso = (request.GET.get("curso") or "").strip()
    if not curso:
        return Response({"detail": "Parámetro 'curso' es requerido."}, status=400)

    if _has_role(request, "Profesores") and not request.user.is_superuser:
        if not _profesor_can_access_curso(request.user, curso):
            return Response({"detail": "No autorizado para ese curso."}, status=403)

    # ✅ FIX: si Alumno no tiene apellido, no explota
    if _has_model_field(Alumno, "apellido"):
        qs = Alumno.objects.filter(curso=curso).order_by("apellido", "nombre")
    else:
        qs = Alumno.objects.filter(curso=curso).order_by("nombre")

    return Response(_build_alumnos_payload(qs), status=200)


# =========================================================
#  ✅ NUEVO: endpoint compatible con tu front:
#      GET /api/alumnos/curso/<curso>/
# =========================================================
@csrf_exempt
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def alumnos_por_curso_path(request, curso: str):
    """
    GET /api/alumnos/curso/<curso>/

    Este endpoint existe porque tu front está pidiendo:
      /api/alumnos/curso/1A/

    y antes solo existía:
      /api/alumnos/?curso=1A
    """
    curso = (curso or "").strip()
    if not curso:
        return Response({"detail": "curso vacío."}, status=400)

    if _has_role(request, "Profesores") and not request.user.is_superuser:
        if not _profesor_can_access_curso(request.user, curso):
            return Response({"detail": "No autorizado para ese curso."}, status=403)

    if _has_model_field(Alumno, "apellido"):
        qs = Alumno.objects.filter(curso=curso).order_by("apellido", "nombre")
    else:
        qs = Alumno.objects.filter(curso=curso).order_by("nombre")

    return Response(_build_alumnos_payload(qs), status=200)


# =========================================================
#  🔎 API Detalle de Alumno (preferir legajo sobre PK)
# =========================================================
@csrf_exempt
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def alumno_detalle(request, alumno_id):
    """
    GET /api/alumnos/<alumno_id>/

    Prioridad de resolución:
      1) Buscar por legajo `id_alumno` (string exacto).
      2) Si no existe y es numérico, intentar como PK (id interno).
    """
    try:
        # 1) intentar por legajo
        a = Alumno.objects.get(id_alumno=str(alumno_id))
    except Alumno.DoesNotExist:
        # 2) fallback a PK si es numérico
        if str(alumno_id).isdigit():
            try:
                a = Alumno.objects.get(pk=int(alumno_id))
            except Alumno.DoesNotExist:
                return Response({"detail": "No encontrado"}, status=404)
        else:
            return Response({"detail": "No encontrado"}, status=404)

    # ✅ NUEVO: autorización consistente (incluye preceptor por curso)
    user = request.user
    is_padre = (getattr(a, "padre_id", None) == user.id)
    is_prof_ok = _has_role(request, "Profesores") and _profesor_can_access_alumno(user, a)
    is_prof_or_super = (user.is_superuser or is_prof_ok)
    # Alumno propio:
    # - Vínculo explícito Alumno.usuario (si existe)
    # - Fallback robusto (username==legajo, padre con único hijo, etc.)
    is_alumno_mismo = False
    try:
        is_alumno_mismo = (getattr(a, "usuario_id", None) == user.id)
    except Exception:
        is_alumno_mismo = False
    if not is_alumno_mismo:
        try:
            r = resolve_alumno_for_user(user)
            if r.alumno and r.alumno.id == a.id:
                is_alumno_mismo = True
        except Exception:
            pass
    is_preceptor_ok = (_has_role(request, "Preceptores") and _preceptor_can_access_alumno(user, a))

    if not (is_padre or is_prof_or_super or is_alumno_mismo or is_preceptor_ok):
        return Response({"detail": "No autorizado"}, status=403)

    return Response(AlumnoFullSerializer(a).data)


# =========================================================
#  📘 API Notas de un alumno (preferir legajo sobre PK)
# =========================================================
@csrf_exempt
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def alumno_notas(request, alumno_id):
    """
    GET /api/alumnos/<alumno_id>/notas/

    Prioridad de resolución:
      1) Buscar por legajo `id_alumno`.
      2) Si no existe y es numérico, intentar como PK (id).
    """
    try:
        alumno = Alumno.objects.get(id_alumno=str(alumno_id))
    except Alumno.DoesNotExist:
        if str(alumno_id).isdigit():
            try:
                alumno = Alumno.objects.get(pk=int(alumno_id))
            except Alumno.DoesNotExist:
                return Response({"detail": "Alumno no encontrado"}, status=404)
        else:
            return Response({"detail": "Alumno no encontrado"}, status=404)

    user = request.user

    # Alumno propio (mismo criterio que en alumno_detalle)
    is_alumno_mismo = False
    try:
        is_alumno_mismo = (getattr(alumno, "usuario_id", None) == user.id)
    except Exception:
        is_alumno_mismo = False
    if not is_alumno_mismo:
        try:
            r = resolve_alumno_for_user(user)
            if r.alumno and r.alumno.id == alumno.id:
                is_alumno_mismo = True
        except Exception:
            pass

    # ✅ NUEVO: sumar Preceptores (pero solo si tienen el curso asignado)
    is_preceptor_ok = (_has_role(request, "Preceptores") and _preceptor_can_access_alumno(user, alumno))
    is_prof_ok = (_has_role(request, "Profesores") and _profesor_can_access_alumno(user, alumno))

    # Autorización: superuser, profesores, preceptor por curso, padre o el propio alumno
    if not (
        user.is_superuser
        or is_prof_ok
        or is_preceptor_ok
        or alumno.padre_id == user.id
        or is_alumno_mismo
    ):
        return Response({"detail": "No autorizado"}, status=403)

    qs = Nota.objects.filter(alumno=alumno)
    # Orden consistente: por cuatrimestre y, si existe, por fecha
    if any(f.name == 'fecha' for f in Nota._meta.fields):
        qs = qs.order_by('cuatrimestre', 'fecha', 'materia')
    else:
        qs = qs.order_by('cuatrimestre', 'materia')

    data = NotaPublicSerializer(qs, many=True).data
    return Response({
        "alumno": {"id": alumno.id, "id_alumno": alumno.id_alumno, "nombre": alumno.nombre},
        "notas": data
    })


# =========================================================
#  Notas
# =========================================================
@login_required
def agregar_nota(request):
    if not (_has_role(request, 'Profesores') or request.user.is_superuser):
        return HttpResponse("No tenés permiso.", status=403)

    cursos = getattr(Alumno, 'CURSOS', [])
    curso_seleccionado = request.GET.get('curso') or request.POST.get('curso')
    if _has_role(request, "Profesores") and not request.user.is_superuser:
        asignados = _profesor_cursos_asignados(request.user)
        if asignados:
            asignados_set = set(asignados)
            cursos = [c for c in cursos if c[0] in asignados_set]
            if curso_seleccionado and curso_seleccionado not in asignados_set:
                return HttpResponse("No tenés permiso para ese curso.", status=403)

    if request.method == 'POST':
        alumnos_list = request.POST.getlist('alumno[]')
        if alumnos_list:
            materias_list = request.POST.getlist('materia[]')
            tipos_list = request.POST.getlist('tipo[]')
            califs_list = request.POST.getlist('calificacion[]')
            cuatris_list = request.POST.getlist('cuatrimestre[]')
            fechas_list = request.POST.getlist('fecha[]')

            creadas = 0
            errores = 0
            notas_creadas = []
            n = min(len(alumnos_list), len(materias_list), len(tipos_list),
                    len(califs_list), len(cuatris_list), len(fechas_list))

            for i in range(n):
                alum_id = (alumnos_list[i] or '').strip()
                materia = (materias_list[i] or '').strip()
                tipo = (tipos_list[i] or '').strip()
                calif = (califs_list[i] or '').strip()
                cuatr = (cuatris_list[i] or '').strip()
                fstr = (fechas_list[i] or '').strip()
                fparsed = parse_date(fstr) if fstr else None

                if not (alum_id and materia and tipo and calif and cuatr and fparsed):
                    continue

                try:
                    alumno = Alumno.objects.get(id_alumno=alum_id)
                    calif_norm = calif.strip().upper()
                    nota = Nota(
                        alumno=alumno,
                        materia=materia,
                        tipo=tipo,
                        calificacion=calif_norm,
                        cuatrimestre=int(cuatr),
                        fecha=fparsed
                    )
                    nota.full_clean()
                    nota.save()

                    notas_creadas.append(nota)

                    creadas += 1
                except (Alumno.DoesNotExist, ValidationError, Exception):
                    errores += 1
                    continue

            # Notificación optimizada: en lote (1 por alumno)
            try:
                _notify_padres_por_notas_bulk(request.user, notas_creadas)
            except Exception:
                pass

            if creadas:
                messages.success(request, f"✅ Se guardaron {creadas} nota(s).")
            if errores:
                messages.error(request, f"⚠️ {errores} fila(s) no pudieron guardarse. Revisá los datos.")
            return redirect(f"{request.path}?curso={curso_seleccionado or ''}")

        alumno_id = request.POST.get('alumno')
        materia = request.POST.get('materia')
        tipo = request.POST.get('tipo')
        calificacion = request.POST.get('calificacion')
        cuatrimestre = request.POST.get('cuatrimestre')
        fecha_nota = parse_date(request.POST.get('fecha') or '') or date.today()

        try:
            alumno = Alumno.objects.get(id_alumno=alumno_id)
            calif_norm = (calificacion or "").strip().upper()
            nota = Nota(
                alumno=alumno,
                materia=materia or "",
                tipo=tipo or "",
                calificacion=calif_norm,
                cuatrimestre=int(cuatrimestre),
                fecha=fecha_nota
            )
            nota.full_clean()
            nota.save()

            # Notificar al padre (campanita)
            try:
                _notify_padre_por_nota(request.user, nota)
            except Exception:
                pass

            messages.success(request, "✅ Nota guardada correctamente.")
        except Alumno.DoesNotExist:
            messages.error(request, "❌ Alumno no encontrado.")
        except ValidationError as e:
            messages.error(request, f"❌ Calificación inválida: {e}")
        except Exception as e:
            messages.error(request, f"❌ No se pudo guardar la nota: {e}")
        return redirect('index')

    alumnos = []
    if curso_seleccionado:
        alumnos = Alumno.objects.filter(curso=curso_seleccionado).order_by('nombre')

    return render(request, 'calificaciones/agregar_nota.html', {
        'cursos': cursos,
        'curso_seleccionado': curso_seleccionado,
        'alumnos': alumnos,
        'materias': MATERIAS
    })


@csrf_exempt
@login_required
def agregar_nota_masiva(request):
    if not (_has_role(request, 'Profesores') or request.user.is_superuser):
        return HttpResponse("No tenés permiso.", status=403)

    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    if _has_role(request, "Profesores") and not request.user.is_superuser:
        asignados = _profesor_cursos_asignados(request.user)
        if asignados:
            curso_qs = (request.POST.get("curso") or "").strip()
            if curso_qs and curso_qs not in asignados:
                return JsonResponse({"detail": "No autorizado para ese curso."}, status=403)

    alumnos_ids = request.POST.getlist('alumno[]')
    materias = request.POST.getlist('materia[]')
    tipos = request.POST.getlist('tipo[]')
    califs = request.POST.getlist('calificacion[]')
    cuatris = request.POST.getlist('cuatrimestre[]')
    fechas = request.POST.getlist('fecha[]')

    if not alumnos_ids and request.POST.get('alumno'):
        alumnos_ids = [request.POST.get('alumno')]
        materias = [request.POST.get('materia')]
        tipos = [request.POST.get('tipo')]
        califs = [request.POST.get('calificacion')]
        cuatris = [request.POST.get('cuatrimestre')]
        fechas = [request.POST.get('fecha')] if request.POST.get('fecha') else []

    n = min(len(alumnos_ids), len(materias), len(tipos), len(califs), len(cuatris))
    if n == 0:
        return JsonResponse({'ok': False, 'creadas': 0, 'detail': 'Sin filas válidas'}, status=400)

    has_fecha = any(f.name == 'fecha' for f in Nota._meta.fields)

    objs = []
    errores = 0
    for i in range(n):
        alum_id = (alumnos_ids[i] or '').strip()
        materia = (materias[i] or '').strip()
        tipo = (tipos[i] or '').strip()
        calif = (califs[i] or '').strip()
        cuatr = (cuatris[i] or '').strip()
        if not (alum_id and materia and tipo and calif):
            errores += 1
            continue

        try:
            alumno = Alumno.objects.get(id_alumno=alum_id)
        except Alumno.DoesNotExist:
            errores += 1
            continue

        kwargs = dict(
            alumno=alumno,
            materia=materia,
            tipo=tipo,
            calificacion=calif.strip().upper(),
            cuatrimestre=int(cuatris[i] or 0),
        )
        if has_fecha and i < len(fechas) and fechas[i]:
            f = parse_date(fechas[i])
            if f:
                kwargs['fecha'] = f

        try:
            nota = Nota(**kwargs)
            nota.full_clean()
            objs.append(nota)
        except ValidationError:
            errores += 1
        except Exception:
            errores += 1

    creadas = 0
    if objs:
        Nota.objects.bulk_create(objs)
        creadas = len(objs)

        # Notificación optimizada: en lote (1 por alumno)
        try:
            _notify_padres_por_notas_bulk(request.user, objs)
        except Exception:
            pass

    accept = (request.headers.get('Accept') or '').lower()
    curso_qs = request.POST.get('curso') or ''
    if 'text/html' in accept:
        return redirect(f"/agregar_nota?curso={curso_qs}")

    return JsonResponse({'ok': True, 'creadas': creadas, 'errores': errores})


@login_required
def ver_notas(request):
    # Permitir ver esta pantalla si la vista previa es "Padres"
    if _has_role(request, 'Padres') or request.user.is_superuser:
        alumnos = Alumno.objects.filter(padre=request.user)

        # Fallback para vista previa: tomar un padre real y sus hijos si no hay vínculos
        if not alumnos.exists() and _get_preview_role(request):
            a0 = Alumno.objects.filter(padre__isnull=False).order_by('padre_id').first()
            if a0 and a0.padre_id:
                alumnos = Alumno.objects.filter(padre_id=a0.padre_id)

        notas = Nota.objects.filter(alumno__in=alumnos).order_by('cuatrimestre')
        return render(request, 'calificaciones/ver_notas.html', {'notas': notas})
    else:
        return HttpResponse("No tienes permiso para ver notas.", status=403)


# =========================================================
#  Mensajería (HTML)
# =========================================================
@login_required
def enviar_mensaje(request):
    if not (_has_role(request, 'Profesores') or request.user.is_superuser):
        return HttpResponse("No tenés permiso.", status=403)

    cursos_disponibles = Alumno.CURSOS
    curso_seleccionado = request.GET.get('curso')
    if _has_role(request, "Profesores") and not request.user.is_superuser:
        asignados = _profesor_cursos_asignados(request.user)
        if asignados:
            asignados_set = set(asignados)
            cursos_disponibles = [c for c in cursos_disponibles if c[0] in asignados_set]
            if curso_seleccionado and curso_seleccionado not in asignados_set:
                return HttpResponse("No tenés permiso para ese curso.", status=403)
    alumnos = Alumno.objects.filter(curso=curso_seleccionado) if curso_seleccionado else []

    if request.method == 'POST':
        alumno_id = request.POST['alumno']
        asunto = request.POST['asunto']
        contenido = request.POST['contenido']
        alumno = Alumno.objects.get(id=alumno_id)
        receptor = alumno.padre

        if receptor:
            sf = _mensaje_sender_field()
            rf = _mensaje_recipient_field()
            cf = _mensaje_curso_field()

            kwargs = {
                sf: request.user,
                rf: receptor,
                "asunto": asunto,
                "contenido": contenido,
            }
            if cf:
                kwargs[cf] = getattr(alumno, "curso", None)

            msg = Mensaje.objects.create(**kwargs)
            try:
                contenido_corto = (contenido[:160] + "...") if len(contenido) > 160 else contenido
                url = "/mensajes"
                if hasattr(msg, "thread_id") and getattr(msg, "thread_id", None):
                    url = f"/mensajes/hilo/{getattr(msg, 'thread_id')}"
                actor_label = (request.user.get_full_name() or request.user.username or "Usuario").strip()
                titulo = f"{actor_label}: {asunto}" if asunto else f"Nuevo mensaje de {actor_label}"
                Notificacion.objects.create(
                    destinatario=receptor,
                    tipo="mensaje",
                    titulo=titulo,
                    descripcion=contenido_corto.strip() or None,
                    url=url,
                    leida=False,
                    meta={
                        "mensaje_id": getattr(msg, "id", None),
                        "thread_id": str(getattr(msg, "thread_id", "")) if hasattr(msg, "thread_id") else str(getattr(msg, "id", "")),
                        "curso": getattr(alumno, "curso", "") if alumno else "",
                        "remitente_id": getattr(request.user, "id", None),
                        "alumno_id": getattr(alumno, "id", None) if alumno else None,
                    },
                )
            except Exception:
                pass
            return redirect('index')
        else:
            return HttpResponse("Este alumno no tiene padre asignado.", status=400)

    return render(request, 'calificaciones/enviar_mensaje.html', {
        'cursos': cursos_disponibles,
        'curso_seleccionado': curso_seleccionado,
        'alumnos': alumnos
    })


@login_required
def enviar_comunicado(request):
    if not (_has_role(request, 'Profesores') or request.user.is_superuser):
        return HttpResponse("No tenés permiso.", status=403)

    cursos = Alumno.CURSOS
    if _has_role(request, "Profesores") and not request.user.is_superuser:
        asignados = _profesor_cursos_asignados(request.user)
        if asignados:
            asignados_set = set(asignados)
            cursos = [c for c in cursos if c[0] in asignados_set]

    if request.method == 'POST':
        curso = request.POST['curso']
        if _has_role(request, "Profesores") and not request.user.is_superuser:
            asignados = _profesor_cursos_asignados(request.user)
            if asignados and curso not in set(asignados):
                return HttpResponse("No tenés permiso para ese curso.", status=403)
        asunto = request.POST['asunto']
        contenido = request.POST['contenido']
        alumnos = Alumno.objects.filter(curso=curso, padre__isnull=False)

        sf = _mensaje_sender_field()
        rf = _mensaje_recipient_field()
        cf = _mensaje_curso_field()

        notifs = []
        for alumno in alumnos:
            kwargs = {
                sf: request.user,
                rf: alumno.padre,
                "asunto": asunto,
                "contenido": contenido,
            }
            if cf:
                kwargs[cf] = curso
            msg = Mensaje.objects.create(**kwargs)
            try:
                contenido_corto = (contenido[:160] + "...") if len(contenido) > 160 else contenido
                url = "/mensajes"
                if hasattr(msg, "thread_id") and getattr(msg, "thread_id", None):
                    url = f"/mensajes/hilo/{getattr(msg, 'thread_id')}"
                actor_label = (request.user.get_full_name() or request.user.username or "Usuario").strip()
                titulo = f"{actor_label}: {asunto}" if asunto else f"Nuevo mensaje de {actor_label}"
                notifs.append(
                    Notificacion(
                        destinatario=alumno.padre,
                        tipo="mensaje",
                        titulo=titulo,
                        descripcion=contenido_corto.strip() or None,
                        url=url,
                        leida=False,
                        meta={
                            "mensaje_id": getattr(msg, "id", None),
                            "thread_id": str(getattr(msg, "thread_id", "")) if hasattr(msg, "thread_id") else str(getattr(msg, "id", "")),
                            "curso": curso or "",
                            "remitente_id": getattr(request.user, "id", None),
                            "alumno_id": getattr(alumno, "id", None),
                        },
                    )
                )
            except Exception:
                pass

        if notifs:
            try:
                Notificacion.objects.bulk_create(notifs)
            except Exception:
                pass

        return redirect('index')

    return render(request, 'calificaciones/enviar_comunicado.html', {'cursos': cursos})


# =========================================================
#  ✅ NUEVO: Mensajería API (JSON) para modales del front
# =========================================================
@csrf_exempt
@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser])
def mensajes_enviar_api(request):
    """
    POST /mensajes/enviar/
    Body JSON: { alumno_id (PK) | id_alumno (legajo), asunto, contenido }
    Envía el mensaje al PADRE del alumno. Opcionalmente setea curso_asociado/curso si el modelo lo posee.
    """
    payload = _coerce_json(request)
    alumno_pk = payload.get("alumno_id")
    legajo = payload.get("id_alumno")
    asunto = (payload.get("asunto") or "").strip()
    contenido = (payload.get("contenido") or payload.get("cuerpo") or "").strip()

    if not asunto or not contenido:
        return Response({"detail": "Faltan asunto y/o contenido."}, status=400)

    # Resolver alumno por PK o legajo
    alumno = None
    if alumno_pk:
        try:
            alumno = Alumno.objects.get(pk=int(alumno_pk))
        except Exception:
            return Response({"detail": "alumno_id inválido."}, status=400)
    elif legajo:
        try:
            alumno = Alumno.objects.get(id_alumno=str(legajo))
        except Alumno.DoesNotExist:
            return Response({"detail": "id_alumno no encontrado."}, status=404)
    else:
        return Response({"detail": "Debe enviar alumno_id o id_alumno."}, status=400)

    receptor = getattr(alumno, "padre", None)
    if not receptor:
        return Response({"detail": "El alumno no tiene padre/tutor asignado."}, status=400)

    sf = _mensaje_sender_field()
    rf = _mensaje_recipient_field()
    cf = _mensaje_curso_field()

    kwargs = {
        sf: request.user,
        rf: receptor,
        "asunto": asunto,
        "contenido": contenido
    }
    if cf:
        kwargs[cf] = alumno.curso

    m = Mensaje.objects.create(**kwargs)
    try:
        contenido_corto = (contenido[:160] + "...") if len(contenido) > 160 else contenido
        url = "/mensajes"
        if hasattr(m, "thread_id") and getattr(m, "thread_id", None):
            url = f"/mensajes/hilo/{getattr(m, 'thread_id')}"
        actor_label = (request.user.get_full_name() or request.user.username or "Usuario").strip()
        titulo = f"{actor_label}: {asunto}" if asunto else f"Nuevo mensaje de {actor_label}"
        Notificacion.objects.create(
            destinatario=receptor,
            tipo="mensaje",
            titulo=titulo,
            descripcion=contenido_corto.strip() or None,
            url=url,
            leida=False,
            meta={
                "mensaje_id": getattr(m, "id", None),
                "thread_id": str(getattr(m, "thread_id", "")) if hasattr(m, "thread_id") else str(getattr(m, "id", "")),
                "curso": getattr(alumno, "curso", "") if alumno else "",
                "remitente_id": getattr(request.user, "id", None),
                "alumno_id": getattr(alumno, "id", None) if alumno else None,
            },
        )
    except Exception:
        pass
    return Response({"ok": True, "mensaje_id": m.id}, status=201)


@login_required
def ver_mensajes(request):
    """
    Lista los mensajes recibidos por el usuario autenticado (padre/tutor).
    Evita usar campos inexistentes y ordena por 'fecha_envio' si existe.
    """
    if _has_role(request, 'Padres') or request.user.is_superuser:
        order_field = 'fecha_envio' if _has_model_field(Mensaje, 'fecha_envio') else 'id'

        rf = _mensaje_recipient_field()
        mensajes = Mensaje.objects.filter(**{rf: request.user}).order_by(f'-{order_field}')

        return render(request, 'calificaciones/ver_mensajes.html', {'mensajes': mensajes})
    else:
        return HttpResponse("No tienes permiso para ver mensajes.", status=403)


# =========================================================
#  Boletín / Historial
# =========================================================
@login_required
def generar_boletin_pdf(request, alumno_id):
    alumno = get_object_or_404(Alumno, id_alumno=alumno_id)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="boletin_{alumno.nombre}.pdf'
    p = canvas.Canvas(response)
    p.drawString(100, 800, f"Boletín de {alumno.nombre}")
    y = 750
    notas = Nota.objects.filter(alumno=alumno).order_by('cuatrimestre')
    for nota in notas:
        p.drawString(100, y, f"{nota.materia} - Cuatrimestre {nota.cuatrimestre}: {nota.calificacion}")
        y -= 20
    p.showPage()
    p.save()
    return response


@login_required
def historial_notas_profesor(request, alumno_id):
    if not (_has_role(request, 'Profesores') or request.user.is_superuser):
        return HttpResponse("No tenés permiso para ver esto.", status=403)

    alumno = get_object_or_404(Alumno, id_alumno=alumno_id)
    if _has_role(request, "Profesores") and not request.user.is_superuser:
        if not _profesor_can_access_alumno(request.user, alumno):
            return HttpResponse("No tenés permiso para ese curso.", status=403)
    materias = set(Nota.objects.filter(alumno=alumno).values_list('materia', flat=True))
    materia_seleccionada = request.GET.get('materia')
    notas = []

    if materia_seleccionada:
        notas = Nota.objects.filter(alumno=alumno, materia=materia_seleccionada).order_by('cuatrimestre')

    return render(request, 'calificaciones/historial_notas.html', {
        'alumno': alumno,
        'materias': materias,
        'materia_seleccionada': materia_seleccionada,
        'notas': notas
    })


@login_required
def historial_notas_padre(request):
    if not (_has_role(request, 'Padres') or request.user.is_superuser):
        return HttpResponse("No tenés permiso para ver esto.", status=403)

    alumnos = Alumno.objects.filter(padre=request.user)
    if not alumnos.exists() and _get_preview_role(request):
        a0 = Alumno.objects.filter(padre__isnull=False).order_by('padre_id').first()
        if a0 and a0.padre_id:
            alumnos = Alumno.objects.filter(padre_id=a0.padre_id)
    alumno = alumnos.first()

    materias = set(Nota.objects.filter(alumno=alumno).values_list('materia', flat=True)) if alumno else set()
    materia_seleccionada = request.GET.get('materia')
    notas = []

    if materia_seleccionada and alumno:
        notas = Nota.objects.filter(alumno=alumno, materia=materia_seleccionada).order_by('cuatrimestre')

    return render(request, 'calificaciones/historial_notas.html', {
        'alumno': alumno,
        'materias': materias,
        'materia_seleccionada': materia_seleccionada,
        'notas': notas
    })


# =========================================================
#  API EVENTOS (funcionales)
# =========================================================
@csrf_exempt
@api_view(["GET"])
@permission_classes([AllowAny])
def api_eventos_tipos(request):
    return Response(["examen", "acto", "reunión", "feriado"])


@csrf_exempt
@api_view(["GET", "POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def api_eventos(request):
    user = request.user

    if user.is_superuser or _has_role(request, 'Profesores'):
        qs = Evento.objects.all()
        if _has_role(request, "Profesores") and not user.is_superuser:
            asignados = _profesor_cursos_asignados(user)
            if asignados:
                qs = qs.filter(curso__in=asignados)
    else:
        try:
            alumno = Alumno.objects.get(padre=user)
            qs = Evento.objects.filter(
                Q(curso=alumno.curso)
                | Q(curso__iexact="ALL")
                | Q(curso__iexact="TODOS")
                | Q(curso="*")
            )
        except Alumno.DoesNotExist:
            qs = Evento.objects.none()

    if request.method == "GET":
        ser = EventoSerializer(qs, many=True)
        return Response(ser.data)

    # --- POST crear ---
    payload = _coerce_json(request)
    data = _normalize_event_payload(payload)

    if _has_role(request, "Profesores") and not user.is_superuser:
        asignados = _profesor_cursos_asignados(user)
        if asignados and data.get("curso") not in set(asignados):
            return Response({"detail": "No tenés permiso para ese curso."}, status=403)

    ser = EventoSerializer(data=data)
    if not ser.is_valid():
        logger.warning("❌ Validación evento (POST) fallida. data=%s errors=%s", data, ser.errors)
        return Response(
            {"detail": "Validación fallida", "errors": ser.errors, "data": data},
            status=status.HTTP_400_BAD_REQUEST,
        )

    ser.save(creado_por=user)  # quitar si tu modelo no tiene creado_por
    return Response(ser.data, status=status.HTTP_201_CREATED)


@csrf_exempt
@api_view(["PUT", "PATCH", "DELETE"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def api_evento_detalle(request, pk: int):
    ev = get_object_or_404(Evento, pk=pk)

    if not (request.user.is_superuser or getattr(ev, "creado_por_id", None) == request.user.id):
        return Response({"detail": "No autorizado."}, status=403)

    if request.method in ("PUT", "PATCH"):
        payload = _coerce_json(request)
        data = _normalize_event_payload(payload)
        partial = (request.method == "PATCH")
        ser = EventoSerializer(ev, data=data, partial=partial)
        if not ser.is_valid():
            logger.warning("❌ Validación evento (UPDATE) fallida. data=%s errors=%s", data, ser.errors)
            return Response(
                {"detail": "Validación fallida", "errors": ser.errors, "data": data},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ser.save()
        return Response(ser.data)

    ev.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# =========================================================
#  DRF ViewSet (opcional)
# =========================================================
@method_decorator(csrf_exempt, name="dispatch")
class EventoViewSet(viewsets.ModelViewSet):
    queryset = Evento.objects.all()
    serializer_class = EventoSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = (JWTAuthentication,)
    parser_classes = (JSONParser, FormParser, MultiPartParser)

    @action(detail=False, methods=["get"], url_path="tipos",
            permission_classes=[AllowAny], authentication_classes=[])
    def tipos(self, request):
        return Response(["examen", "acto", "reunión", "feriado"])

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or _has_role(self.request, 'Profesores'):
            qs = Evento.objects.all()
            if _has_role(self.request, "Profesores") and not user.is_superuser:
                asignados = _profesor_cursos_asignados(user)
                if asignados:
                    qs = qs.filter(curso__in=asignados)
            return qs
        try:
            alumno = Alumno.objects.get(padre=user)
            return Evento.objects.filter(curso=alumno.curso)
        except Alumno.DoesNotExist:
            return Evento.objects.none()

    def create(self, request, *args, **kwargs):
        payload = _coerce_json(request)
        data = _normalize_event_payload(payload)
        ser = self.get_serializer(data=data)
        if not ser.is_valid():
            logger.warning("❌ Validación evento (ViewSet.create) fallida. data=%s errors=%s", data, ser.errors)
            return Response({"detail": "Validación fallida", "errors": ser.errors, "data": data},
                            status=status.HTTP_400_BAD_REQUEST)
        self.perform_create(ser)
        return Response(ser.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        payload = _coerce_json(request)
        data = _normalize_event_payload(payload)
        ser = self.get_serializer(instance, data=data, partial=partial)
        if not ser.is_valid():
            logger.warning("❌ Validación evento (ViewSet.update) fallida. data=%s errors=%s", data, ser.errors)
            return Response({"detail": "Validación fallida", "errors": ser.errors, "data": data},
                            status=status.HTTP_400_BAD_REQUEST)
        self.perform_update(ser)
        return Response(ser.data)

    def partial_update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(creado_por=self.request.user)


# =========================================================
#  Vistas HTML calendario
# =========================================================
@login_required
def calendario_view(request):
    form = EventoForm()
    return render(request, 'calificaciones/calendario.html', {'form': form})


@login_required
def crear_evento(request):
    if not (_has_role(request, 'Profesores') or request.user.is_superuser):
        return HttpResponse("No tenés permiso para crear eventos.", status=403)

    asignados = []
    if _has_role(request, "Profesores") and not request.user.is_superuser:
        asignados = _profesor_cursos_asignados(request.user)

    if request.method == 'POST':
        form = EventoForm(request.POST)
        if asignados:
            curso = (request.POST.get("curso") or "").strip()
            if curso and curso not in set(asignados):
                return JsonResponse({"success": False, "detail": "No autorizado para ese curso."}, status=403)
        if form.is_valid():
            evento = form.save(commit=False)
            evento.creado_por = request.user
            evento.save()
            try:
                from .api_eventos import _notify_evento_creado
                _notify_evento_creado(request, evento)
            except Exception:
                pass
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'success': False, 'errors': form.errors}, status=400)

    return JsonResponse({'error': 'Método no permitido'}, status=405)


@login_required
def editar_evento(request, evento_id):
    evento = get_object_or_404(Evento, id=evento_id)

    if not (request.user == evento.creado_por or request.user.is_superuser):
        return HttpResponse("No tenés permiso para editar este evento.", status=403)

    if request.method == 'POST':
        form = EventoForm(request.POST, instance=evento)
        if form.is_valid():
            form.save()
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'success': False, 'errors': form.errors}, status=400)
    else:
        form = EventoForm(instance=evento)
        return render(request, 'calificaciones/parcial_editar_evento.html', {'form': form, 'evento': evento})


@login_required
def eliminar_evento(request, evento_id):
    evento = get_object_or_404(Evento, id=evento_id)

    if not (request.user == evento.creado_por or request.user.is_superuser):
        return HttpResponse("No tenés permiso para eliminar este evento.", status=403)

    if request.method == 'POST':
        evento.delete()
        return redirect('calendario')

    return render(request, 'calificaciones/confirmar_eliminar_evento.html', {'evento': evento})


# =========================================================
#  Asistencias / Perfiles específicos
# =========================================================
@login_required
def pasar_asistencia(request):
    usuario = request.user
    alumnos = []
    curso_id = None
    curso_nombre = None

    if usuario.is_superuser:
        cursos = [{'id': c[0], 'nombre': c[1]} for c in Alumno.CURSOS]
        curso_id = request.GET.get('curso')
        if curso_id:
            curso_nombre = dict(Alumno.CURSOS).get(curso_id)
    else:
        curso_id = obtener_curso_del_preceptor(usuario)
        if not curso_id:
            return render(request, 'calificaciones/error.html', {'mensaje': 'No tenés un curso asignado como preceptor.'})
        curso_nombre = dict(Alumno.CURSOS).get(curso_id)
        cursos = [{'id': curso_id, 'nombre': curso_nombre}]

    if curso_id:
        alumnos = Alumno.objects.filter(curso=curso_id).order_by('nombre')

    if request.method == 'POST':
        fecha_actual = date.today()
        asistencia_objs = []
        ausentes_ids = []
        for alumno in alumnos:
            presente = request.POST.get(f'asistencia_{alumno.id}') == 'on'
            asistencia_objs.append(Asistencia(
                alumno=alumno,
                fecha=fecha_actual,
                presente=presente
            ))
            if not presente:
                ausentes_ids.append(alumno.id)

        Asistencia.objects.filter(alumno__in=alumnos, fecha=fecha_actual).delete()
        Asistencia.objects.bulk_create(asistencia_objs)

        # Notificar inasistencias a padres/alumnos
        try:
            for alumno in alumnos:
                if alumno.id not in ausentes_ids:
                    continue
                destinatarios = _resolver_destinatarios_notif(alumno)
                if not destinatarios:
                    continue
                alumno_nombre = (f"{getattr(alumno, 'apellido', '')} {getattr(alumno, 'nombre', '')}").strip()
                if not alumno_nombre:
                    alumno_nombre = getattr(alumno, "nombre", "") or str(getattr(alumno, "id_alumno", "")) or "Alumno"
                titulo = f"Inasistencia registrada: {alumno_nombre}"
                descripcion = f"Alumno: {alumno_nombre} · Curso: {getattr(alumno, 'curso', '')} · Fecha: {fecha_actual.isoformat()}"
                for dest in destinatarios:
                    Notificacion.objects.create(
                        destinatario=dest,
                        tipo="inasistencia",
                        titulo=titulo,
                        descripcion=descripcion,
                        url=f"/alumnos/{getattr(alumno, 'id', '')}/?tab=asistencias",
                        leida=False,
                        meta={
                            "alumno_id": getattr(alumno, "id", None),
                            "alumno_legajo": getattr(alumno, "id_alumno", None),
                            "curso": getattr(alumno, "curso", ""),
                            "fecha": fecha_actual.isoformat(),
                            "tipo_asistencia": "clases",
                        },
                    )
        except Exception:
            pass

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True})
        return redirect('index')

    return render(request, 'calificaciones/pasar_asistencia.html', {
        'alumnos': alumnos,
        'curso_id': curso_id,
        'curso_nombre': curso_nombre,
        'cursos': cursos
    })


@login_required
def perfil_alumno(request, alumno_id):
    alumno = get_object_or_404(Alumno, id_alumno=alumno_id)

    is_padre = (request.user == alumno.padre)
    is_prof_ok = _has_role(request, 'Profesores') and _profesor_can_access_alumno(request.user, alumno)
    is_prof_or_super = (request.user.is_superuser or is_prof_ok)
    # Alumno propio (mismo criterio que en endpoints API)
    is_alumno_mismo = False
    try:
        is_alumno_mismo = (getattr(alumno, "usuario_id", None) == request.user.id)
    except Exception:
        is_alumno_mismo = False
    if not is_alumno_mismo:
        try:
            r = resolve_alumno_for_user(request.user)
            if r.alumno and r.alumno.id == alumno.id:
                is_alumno_mismo = True
        except Exception:
            pass

    # ✅ NUEVO: permitir preceptor si el curso coincide
    is_preceptor_ok = (_has_role(request, "Preceptores") and _preceptor_can_access_alumno(request.user, alumno))

    if not (is_padre or is_prof_or_super or is_alumno_mismo or is_preceptor_ok):
        return HttpResponse("No tenés permiso para ver este perfil.", status=403)

    # ✅ NUEVO: contamos ausentes como 1 y "tarde" como 0.5
    asistencias_irregulares = Asistencia.objects.filter(alumno=alumno).filter(
        Q(presente=False) | Q(tarde=True)
    ).order_by('-fecha')

    ausentes_cnt = Asistencia.objects.filter(alumno=alumno, presente=False).count()
    tarde_cnt = Asistencia.objects.filter(alumno=alumno, presente=True, tarde=True).count()
    faltas_equivalentes = ausentes_cnt + (tarde_cnt * 0.5)

    return render(request, 'calificaciones/perfil_alumno.html', {
        'alumno': alumno,
        'asistencias_irregulares': asistencias_irregulares,
        'faltas_equivalentes': faltas_equivalentes,
    })


# =========================================================
#  Endpoint JSON minimal legado
# =========================================================
@login_required
def mi_perfil(request):
    """
    Versión minimal (compat): ahora también expone el alumno vinculado si existe,
    para que el front pueda resolver el id incluso si no llama a /api/perfil_api/.
    """
    user = request.user

    # Alumno propio (robusto/retrocompatible)
    r = resolve_alumno_for_user(user)
    alumno_vinculado = r.alumno

    data = {
        "username": user.username,
        "email": user.email,
        "grupos": _effective_groups(request),
        "rol": _rol_principal(user),
        "is_superuser": user.is_superuser,
        "alumno_resolution": {"method": r.method, "candidates": r.candidates},
    }

    if alumno_vinculado:
        data["alumno"] = _alumno_to_dict(alumno_vinculado)
        # compat keys que tu front intenta leer en distintos flujos
        data["alumno_id"] = alumno_vinculado.id
        data["id_alumno"] = alumno_vinculado.id_alumno

    return JsonResponse(data)


# =========================================================
#  Logout de sesión (complementa blacklist de JWT)
# =========================================================
@csrf_exempt
@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([AllowAny])
def auth_logout(request):
    """
    Cierra la sesión de Django si la hubiera (cookie sessionid) y limpia cookies.
    Para JWT, complementamos con /api/token/blacklist/ desde el front.
    """
    try:
        if request.user.is_authenticated:
            dj_logout(request)
    except Exception:
        pass
    resp = JsonResponse({"detail": "ok"})
    # Limpieza defensiva de cookies típicas
    resp.delete_cookie("sessionid")
    resp.delete_cookie("csrftoken")
    return resp


# =========================================================
#  Cambiar contraseña (autenticado)
# =========================================================
@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
@throttle_classes([UserRateThrottle])
def auth_change_password(request):
    user = request.user
    data = request.data or {}

    current = (data.get("current_password") or data.get("password_actual") or "").strip()
    new = (data.get("new_password") or data.get("password_nueva") or "").strip()

    if not current or not new:
        return Response({"detail": "Completá la contraseña actual y la nueva."}, status=400)

    if len(new) < 6:
        return Response({"detail": "La contraseña nueva debe tener al menos 6 caracteres."}, status=400)

    if not user.check_password(current):
        return Response({"detail": "La contraseña actual no coincide."}, status=400)

    user.set_password(new)
    user.save(update_fields=["password"])

    # Revocar refresh tokens existentes si blacklist está habilitado
    try:
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
        tokens = OutstandingToken.objects.filter(user=user)
        for tok in tokens:
            BlacklistedToken.objects.get_or_create(token=tok)
    except Exception:
        pass

    # Mantener la sesión de Django si estuviera usando cookies
    try:
        update_session_auth_hash(request, user)
    except Exception:
        pass

    return Response({"detail": "Contraseña actualizada."})


# =========================================================
#  ✅ NUEVO: contador de no leídos para el badge de la topbar
# =========================================================
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mensajes_unread_count(request):
    user = request.user
    inbox_qs = _mensajes_inbox_qs(user)

    if _has_model_field(Mensaje, "leido") and _has_model_field(Mensaje, "leido_en"):
        count = inbox_qs.filter(Q(leido=False) | Q(leido_en__isnull=True)).count()
    elif _has_model_field(Mensaje, "leido"):
        count = inbox_qs.filter(leido=False).count()
    elif _has_model_field(Mensaje, "leido_en"):
        count = inbox_qs.filter(leido_en__isnull=True).count()
    elif _has_model_field(Mensaje, "fecha_lectura"):
        count = inbox_qs.filter(fecha_lectura__isnull=True).count()
    else:
        count = 0

    return Response({"count": count})
