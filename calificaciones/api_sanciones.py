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
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import Alumno, Sancion, Notificacion
from .serializers import SancionPublicSerializer
from .views import CsrfExemptSessionAuthentication  # mismo patrón que en mensajes

# ✅ FIX CLAVE: antes no existía User y las notificaciones fallaban silenciosamente
User = get_user_model()


# =========================================================
# Helpers
# =========================================================
def _resolver_alumno_id(valor: Any) -> Optional[Alumno]:
    """
    Acepta PK (int), id_alumno (legajo) o string convertible.

    FIX SOLIDO:
    - Si viene numérico, probamos primero como PK.
    - Si ese PK no existe, caemos a id_alumno (legajo).
    Esto evita que un legajo numérico se interprete como PK incorrecto.
    """
    if valor is None:
        return None

    try:
        sv = str(valor).strip()
        if not sv:
            return None

        # 1) Intentar PK si es dígito
        if sv.isdigit():
            try:
                return Alumno.objects.get(pk=int(sv))
            except Alumno.DoesNotExist:
                pass

        # 2) Intentar por legajo/id_alumno (case-insensitive)
        return Alumno.objects.filter(id_alumno__iexact=sv).first()

    except Exception:
        return None


def _user_label(user) -> str:
    try:
        full = (user.get_full_name() or "").strip()
        if full:
            return full
        return (getattr(user, "username", "") or "").strip()
    except Exception:
        return ""


def _infer_tipo_remitente(user) -> str:
    """
    Mensaje.tipo_remitente tiene choices (Profesor/Preceptor/Directivo).
    Lo inferimos por grupos para que sea consistente con el resto.
    """
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


def _is_docente_o_preceptor(user) -> bool:
    try:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            return True
        groups = [g.name.lower() for g in user.groups.all()]
        joined = " ".join(groups)
        return ("preceptor" in joined) or ("profesor" in joined) or ("docente" in joined)
    except Exception:
        return False


def _alumno_fullname(a: Alumno) -> str:
    nm = (getattr(a, "nombre", "") or "").strip()
    # En tu proyecto actual Alumno no tiene apellido, pero dejo fallback por compat
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
@authentication_classes([CsrfExemptSessionAuthentication, JWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def sanciones_lista_crear(request):
    """
    GET /api/sanciones/?alumno=ID|LEGAJO&curso=1A
      → lista filtrada

    POST /api/sanciones/
      JSON: { alumno | alumno_id | id_alumno, fecha?, asunto?, mensaje?, tipo? }

    Compat legacy:
      - "asunto" → Sancion.detalle
      - "mensaje" → Sancion.motivo
    """
    if request.method == "GET":
        alumno_q = request.query_params.get("alumno")
        curso_q = request.query_params.get("curso")

        qs = Sancion.objects.all().select_related("alumno").order_by("-fecha", "-id")

        if alumno_q:
            alum = _resolver_alumno_id(alumno_q)
            if not alum:
                return Response({"detail": "Alumno no encontrado."}, status=404)
            qs = qs.filter(alumno=alum)

        if curso_q:
            qs = qs.filter(alumno__curso=curso_q)

        data = SancionPublicSerializer(qs, many=True).data
        return Response({"results": data}, status=200)

    # POST
    if not _is_docente_o_preceptor(request.user):
        return Response({"detail": "No autorizado."}, status=403)

    payload = _get_payload(request)

    alumno_val = payload.get("alumno", payload.get("alumno_id", payload.get("id_alumno")))
    alumno = _resolver_alumno_id(alumno_val)
    if not alumno:
        return Response({"detail": "Debés indicar un alumno válido."}, status=400)

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

    sancion = Sancion.objects.create(
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
        _add(getattr(alumno, "usuario", None))

        # Alumno por convención username==legajo/id_alumno
        try:
            legajo = (getattr(alumno, "id_alumno", "") or "").strip()
            if legajo:
                u_alumno = User.objects.filter(username__iexact=legajo).first()
                _add(u_alumno)
        except Exception:
            pass

        # Fallback legacy: si no hay padre ni usuario alumno, intentar username==id_alumno igual
        if not destinatarios:
            try:
                legajo = (getattr(alumno, "id_alumno", "") or "").strip()
                if legajo:
                    _add(User.objects.filter(username__iexact=legajo).first())
            except Exception:
                pass

        if destinatarios:
            alumno_nombre = _alumno_fullname(alumno)
            curso_alumno = getattr(alumno, "curso", "") or ""

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

            contenido_msg = (
                "Se registró una sanción disciplinaria.\n\n"
                f"Alumno: {alumno_nombre}\n"
                + (f"Curso: {curso_alumno}\n" if curso_alumno else "")
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
                    destinatario=destinatario,
                    tipo="sancion",
                    titulo=asunto_msg,
                    descripcion=contenido_msg,
                    url=url_sanc,
                    leida=False,
                    meta={
                        "alumno_id": getattr(alumno, "id", None),
                        "alumno_legajo": getattr(alumno, "id_alumno", None),
                        "curso": curso_alumno or "",
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
        "ok": True,
        "id": sancion.id,
        "notificado": notificado,
        "notif_destinatario_id": notif_destinatario_id,
        "notif_source": notif_source,
    }

    if (not notificado) and notif_error and (
        getattr(request.user, "is_staff", False) or getattr(request.user, "is_superuser", False)
    ):
        resp["notif_error"] = notif_error

    return Response(resp, status=201)


@csrf_exempt
@api_view(["GET", "DELETE"])
@authentication_classes([CsrfExemptSessionAuthentication, JWTAuthentication])
@permission_classes([IsAuthenticated])
def sancion_detalle(request, pk: int):
    """
    GET /api/sanciones/<id>/   → detalle
    DELETE /api/sanciones/<id>/ → elimina
    """
    try:
        sanc = Sancion.objects.select_related("alumno").get(pk=pk)
    except Sancion.DoesNotExist:
        return Response({"detail": "No encontrada."}, status=404)

    if request.method == "GET":
        return Response(SancionPublicSerializer(sanc).data, status=200)

    if not _is_docente_o_preceptor(request.user):
        return Response({"detail": "No autorizado."}, status=403)

    sanc.delete()
    return Response(status=204)
