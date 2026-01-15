# calificaciones/api_nueva_nota.py
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import ValidationError

from rest_framework import status, permissions
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import Alumno, Nota, Mensaje, Notificacion
from .serializers import AlumnoSerializer, NotaCreateSerializer
from .contexto import build_context_for_user, alumno_to_dict

# ---------- Catálogo (con fallbacks) ----------
try:
    from .constants import MATERIAS as MATERIAS_CATALOGO
except Exception:
    MATERIAS_CATALOGO = None


def _materias_por_defecto():
    return getattr(
        settings,
        "MATERIAS_DEFAULT",
        [
            "Matemática", "Lengua", "Ciencias Naturales", "Ciencias Sociales",
            "Inglés", "Educación Física", "Tecnología", "Arte",
        ],
    )


def _tipos_por_defecto():
    try:
        return [t[0] for t in Nota.TIPO_NOTA_CHOICES]
    except Exception:
        return ["Examen", "Trabajo Práctico", "Participación", "Proyecto"]


def _cuatris_por_defecto():
    try:
        return [c[0] for c in Nota.CUATRIMESTRE_CHOICES]
    except Exception:
        return [1, 2]


def get_materias_catalogo():
    return list(MATERIAS_CATALOGO) if MATERIAS_CATALOGO else _materias_por_defecto()


def _cursos_catalogo():
    """Devuelve [{'id': '1A', 'nombre': '1° A'}, ...] desde Alumno.CURSOS si existe."""
    try:
        return [{"id": c[0], "nombre": c[1]} for c in getattr(Alumno, "CURSOS", [])]
    except Exception:
        # Fallback muy básico si no hay choices
        cursos = sorted(set(Alumno.objects.values_list("curso", flat=True)))
        return [{"id": c, "nombre": str(c)} for c in cursos if c]


# ---------- WhoAmI ----------
class WhoAmI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        u = request.user
        groups = list(u.groups.values_list("name", flat=True))

        # Vista previa de rol para superusuario (respeta X-Preview-Role / ?view_as=)
        try:
            from .views import _get_preview_role
            preview_role = _get_preview_role(request)
        except Exception:
            preview_role = None
        if preview_role and getattr(u, "is_superuser", False):
            groups = [preview_role]

        full_name = (u.get_full_name() or f"{u.first_name} {u.last_name}").strip()

        # Contexto de usuario (robusto/retrocompatible) para que el front pueda
        # resolver "quién es el alumno" sin depender de vínculos frágiles.
        ctx = build_context_for_user(u, groups)

        # Vista previa (superusuario): si simula un rol y no hay contexto real, proveo un fallback razonable.
        if preview_role and getattr(u, "is_superuser", False):
            try:
                if "Alumnos" in groups and not ctx.get("alumno"):
                    a0 = Alumno.objects.order_by("id").first()
                    ctx["alumno"] = alumno_to_dict(a0)
                    ctx["alumno_resolution"] = {"method": "preview_first", "candidates": 1 if a0 else 0}
                if "Padres" in groups and not ctx.get("hijos"):
                    a0 = Alumno.objects.filter(padre__isnull=False).order_by("padre_id", "id").first()
                    if a0 and a0.padre_id:
                        hijos = Alumno.objects.filter(padre_id=a0.padre_id).order_by("curso", "nombre")
                        ctx["hijos"] = [alumno_to_dict(x) for x in hijos]
            except Exception:
                pass

        # `alumno` / `hijos` van arriba para compat con el front actual.
        rol = groups[0] if groups else "—"

        return Response(
            {
                "id": u.id,
                "username": u.username,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "full_name": full_name,
                "email": u.email,
                "groups": groups,
                "rol": rol,
                "is_superuser": u.is_superuser,
                "is_staff": u.is_staff,
                **ctx,
            },
            status=status.HTTP_200_OK,
        )


# ---------- Datos iniciales para “Nueva Nota” ----------
class NuevaNotaDatosIniciales(APIView):
    """
    GET /api/calificaciones/nueva-nota/datos/?curso=1A
    Devuelve alumnos (opcionalmente filtrados por curso),
    catálogo de materias, tipos y cuatrimestres.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        curso = request.query_params.get("curso")
        alumnos_qs = Alumno.objects.all().order_by("nombre")
        if curso:
            alumnos_qs = alumnos_qs.filter(curso=curso)

        data = {
            "alumnos": AlumnoSerializer(alumnos_qs, many=True).data,
            "materias": get_materias_catalogo(),
            "tipos": _tipos_por_defecto(),
            "cuatrimestres": _cuatris_por_defecto(),
            "hoy": timezone.localdate(),
        }
        return Response(data, status=status.HTTP_200_OK)


# ---------- Catálogo para el front (endpoint espejo de /notas/catalogos/) ----------
@method_decorator(csrf_exempt, name="dispatch")
class CatalogosNuevaNota(APIView):
    """
    GET /notas/catalogos/
    Estructura compatible con el front:
    {
      "cursos": [{"id","nombre"}],
      "materias": [...],
      "tipos": [...],
      "cuatrimestres": [...],
      "hoy": "YYYY-MM-DD"
    }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        return Response(
            {
                "cursos": _cursos_catalogo(),
                "materias": get_materias_catalogo(),
                "tipos": _tipos_por_defecto(),
                "cuatrimestres": _cuatris_por_defecto(),
                "hoy": timezone.localdate(),
            },
            status=status.HTTP_200_OK,
        )


# ---------- Alumnos por curso (endpoint espejo de /alumnos/?curso=) ----------
@method_decorator(csrf_exempt, name="dispatch")
class AlumnosPorCurso(APIView):
    """
    GET /alumnos/?curso=1A
    Devuelve {"alumnos": [ ... ]}
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        curso = (request.query_params.get("curso") or "").strip()
        if not curso:
            return Response({"detail": "Parámetro 'curso' es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        qs = Alumno.objects.filter(curso=curso).order_by("nombre")
        data = AlumnoSerializer(qs, many=True).data
        return Response({"alumnos": data}, status=status.HTTP_200_OK)


# ---------- Helpers para mapear alumno ----------
def _resolver_alumno_id(valor):
    """
    Acepta:
    - PK numérica (str o int)
    - Legajo 'id_alumno' (str no numérico)
    Devuelve instancia de Alumno o None.
    """
    if valor is None:
        return None
    try:
        sv = str(valor).strip()
        if sv.isdigit():
            return Alumno.objects.get(pk=int(sv))
        # si no es dígito intento por id_alumno (legajo)
        return Alumno.objects.get(id_alumno=sv)
    except Alumno.DoesNotExist:
        return None


def _normalizar_nota_payload(d):
    """
    Convierte {'alumno_id': X} o {'id_alumno': Y} en {'alumno': pk}
    (sin tocar el resto de campos).
    """
    data = dict(d or {})
    if "alumno" not in data:
        if "alumno_id" in data:
            data["alumno"] = data.pop("alumno_id")
        elif "id_alumno" in data:
            data["alumno"] = data.pop("id_alumno")
    # Si alumno es legajo o string, lo convierto a pk
    alumno_val = data.get("alumno", None)
    if alumno_val is not None:
        inst = _resolver_alumno_id(alumno_val)
        if inst:
            data["alumno"] = inst.pk
    return data




# ---------- Notificación: nota nueva → padre (campanita) ----------
def _infer_tipo_remitente(user) -> str:
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


def _resolver_padre_destinatario(alumno: Alumno):
    """Devuelve (user_destinatario, source_str).

    Source puede ser:
      - 'alumno.padre'
      - 'username==id_alumno' (fallback legacy)
      - None
    """
    padre = getattr(alumno, "padre", None)
    if padre is not None:
        return padre, "alumno.padre"

    # Fallback legacy: usuario cuyo username coincide con el legajo (id_alumno)
    try:
        User = get_user_model()
        legajo = (getattr(alumno, "id_alumno", "") or "").strip()
        if legajo:
            u = User.objects.filter(username__iexact=legajo).first()
            if u is not None:
                return u, "username==id_alumno"
    except Exception:
        pass

    return None, None




def _resolver_destinatarios_notif(alumno: Alumno):
    """Destinatarios de notificación:
    - Padre asignado (alumno.padre) si existe
    - Alumno (User.username == alumno.id_alumno) si existe
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

    # Padre explícito
    padre = getattr(alumno, "padre", None)
    if padre is not None:
        _add(padre)

    # Alumno explícito (campo Alumno.usuario)
    _add(getattr(alumno, "usuario", None))

    # Alumno por convención username==legajo/id_alumno
    try:
        User = get_user_model()
        legajo = (getattr(alumno, "id_alumno", "") or "").strip()
        if legajo:
            u_alumno = User.objects.filter(username__iexact=legajo).first()
            if u_alumno is not None:
                _add(u_alumno)
    except Exception:
        pass

    # Fallback legacy (si no hay nada)
    if not destinatarios:
        try:
            u_fb, _src = _resolver_padre_destinatario(alumno)
            if u_fb is not None:
                _add(u_fb)
        except Exception:
            pass

    return destinatarios
def _alumno_nombre(alumno: Alumno) -> str:
    nm = (getattr(alumno, "nombre", "") or "").strip()
    ap = (getattr(alumno, "apellido", "") or "").strip()
    full = (f"{nm} {ap}").strip()
    return full or nm or str(getattr(alumno, "id_alumno", "")) or "Alumno"


def _notify_padre_nota(remitente, nota: Nota):
    # Notificación: nota nueva (campanita) → PADRE y ALUMNO
    try:
        alumno = getattr(nota, "alumno", None)
        if alumno is None:
            return False, None, None, "nota sin alumno"

        destinatarios = _resolver_destinatarios_notif(alumno)
        if not destinatarios:
            return False, None, None, "sin destinatarios"

        docente_label = ""
        try:
            if remitente is not None:
                docente_label = (
                    getattr(remitente, "get_full_name", lambda: "")() or getattr(remitente, "username", "") or ""
                )
        except Exception:
            docente_label = ""

        alumno_nombre = _alumno_fullname(alumno)
        curso_alumno = getattr(alumno, "curso", "") or ""

        materia = getattr(nota, "materia", None)
        materia_nombre = getattr(materia, "nombre", materia) if materia else ""
        tipo = getattr(nota, "tipo", "") or ""
        calif = getattr(nota, "calificacion", None)

        fecha = getattr(nota, "fecha", None)
        fecha_str = fecha.isoformat() if fecha else ""

        asunto_msg = f"Nueva nota para {alumno_nombre}"

        contenido_msg = (
            "Se registraron nuevas calificaciones. "
            f"Alumno: {alumno_nombre} "
            + (f"Curso: {curso_alumno} " if curso_alumno else "")
            + (f"Materia: {materia_nombre} " if materia_nombre else "")
            + (f"Tipo: {tipo} " if tipo else "")
            + (f"Calificación: {calif} " if calif is not None else "")
            + (f"Fecha: {fecha_str} " if fecha_str else "")
            + (f"Docente: {docente_label}" if docente_label else "")
        ).strip()

        notificado = False
        last_id = None

        for destinatario in destinatarios:
            Notificacion.objects.create(
                destinatario=destinatario,
                tipo="nota",
                titulo=asunto_msg,
                descripcion=contenido_msg,
                url=f"/alumnos/{getattr(alumno, 'id', '')}/?tab=notas",
                leida=False,
                meta={
                    "alumno_id": getattr(alumno, "id", None),
                    "alumno_legajo": getattr(alumno, "id_alumno", None),
                    "curso": curso_alumno or "",
                    "materia": materia_nombre or "",
                    "tipo_nota": tipo or "",
                    "calificacion": calif,
                    "fecha": fecha_str,
                },
            )
            notificado = True
            last_id = getattr(destinatario, "id", None)

        return notificado, last_id, "multi", None
    except Exception as e:
        return False, None, None, str(e)


class CrearNota(APIView):
    """
    POST /api/calificaciones/notas/
    Body JSON: { alumno | alumno_id | id_alumno, materia, tipo, calificacion, cuatrimestre, fecha }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        payload = _normalizar_nota_payload(request.data)
        serializer = NotaCreateSerializer(data=payload)
        if serializer.is_valid():
            nota = serializer.save()
            notificado, notif_dest_id, notif_source, notif_error = _notify_padre_nota(request.user, nota)
            resp = {"ok": True, "id": nota.id, "notificado": notificado, "notif_destinatario_id": notif_dest_id, "notif_source": notif_source}
            # Si sos staff/superuser y falló, devolvemos error para debug
            if (not notificado) and notif_error and (getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_superuser', False)):
                resp["notif_error"] = notif_error
            return Response(resp, status=status.HTTP_201_CREATED)
        return Response({"ok": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


# ---------- Crear varias notas (bulk JSON) ----------
@method_decorator(csrf_exempt, name="dispatch")
class CrearNotasMasivo(APIView):
    """    POST /api/calificaciones/notas/masivo/
    Body JSON:
      {"notas": [{...}, {...}]}

    OPTIMIZADO (Railway-friendly):
    - Resuelve alumnos en 1 query (pk/id_alumno)
    - Valida sin instanciar serializers por fila (evita N queries)
    - bulk_create de Notas (1 insert batch)
    - Notificaciones: 1 por alumno+destinatario (padre/alumno) usando bulk_create

    Cada item puede usar 'alumno', 'alumno_id' (pk) o 'id_alumno' (legajo).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        body = request.data
        notas_in = body.get("notas") if isinstance(body, dict) else None
        if not isinstance(notas_in, list):
            return Response(
                {"ok": False, "error": "Formato inválido: se espera {'notas': [ ... ]}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ------------------------
        # 0) Helpers locales
        # ------------------------
        allowed_materias = {c[0] for c in getattr(Nota, 'MATERIAS', [])} or None
        allowed_tipos = {c[0] for c in getattr(Nota, 'TIPOS', [])} or None

        def _get_alumno_key(item):
            if not isinstance(item, dict):
                return None
            v = item.get('alumno', item.get('alumno_id', item.get('id_alumno')))
            if v is None:
                return None
            sv = str(v).strip()
            return sv or None

        # ------------------------
        # 1) Resolver alumnos en bloque (1 query)
        # ------------------------
        keys = []
        for it in notas_in:
            k = _get_alumno_key(it)
            if k is not None:
                keys.append(k)
        keys_unique = sorted(set(keys))

        alumnos_by_pk = {}
        alumnos_by_legajo_lower = {}

        if keys_unique:
            numeric_ids = []
            legajos = []
            for k in keys_unique:
                if k.isdigit():
                    try:
                        numeric_ids.append(int(k))
                    except Exception:
                        pass
                legajos.append(k)

            # Q por pk e id_alumno (incluye variantes de case)
            q = Q()
            if numeric_ids:
                q |= Q(pk__in=numeric_ids)
            if legajos:
                q |= Q(id_alumno__in=legajos) | Q(id_alumno__in=[x.upper() for x in legajos]) | Q(id_alumno__in=[x.lower() for x in legajos])

            qs = Alumno.objects.filter(q).only('id', 'id_alumno', 'curso', 'padre_id', 'usuario_id', 'nombre', 'apellido')
            for a in qs:
                alumnos_by_pk[a.pk] = a
                try:
                    leg = (getattr(a, 'id_alumno', '') or '').strip()
                    if leg:
                        alumnos_by_legajo_lower[leg.lower()] = a
                except Exception:
                    pass

        def _resolve_alumno(k: str):
            if not k:
                return None
            # si viene numérico, primero intento PK; si no existe, caigo a legajo
            if k.isdigit():
                try:
                    a = alumnos_by_pk.get(int(k))
                    if a is not None:
                        return a
                except Exception:
                    pass
            return alumnos_by_legajo_lower.get(k.lower())

        # ------------------------
        # 2) Validación rápida + construcción de Nota objs
        # ------------------------
        errors = []
        notas_objs = []
        today = timezone.localdate()

        for idx, item in enumerate(notas_in):
            if not isinstance(item, dict):
                errors.append({"index": idx, "errors": {"__all__": ["Item inválido (no es objeto)"]}})
                continue

            alumno_key = _get_alumno_key(item)
            alumno = _resolve_alumno(alumno_key) if alumno_key else None
            if alumno is None:
                errors.append({"index": idx, "errors": {"alumno": ["Alumno inválido o inexistente."]}})
                continue

            materia = (item.get('materia') or '').strip()
            tipo = (item.get('tipo') or '').strip()
            calif_raw = item.get('calificacion')
            calif = str(calif_raw or '').strip()
            cuatri_raw = item.get('cuatrimestre')
            fecha_raw = item.get('fecha', None)

            row_err = {}

            if not materia:
                row_err.setdefault('materia', []).append('Materia requerida.')
            elif allowed_materias is not None and materia not in allowed_materias:
                row_err.setdefault('materia', []).append('Materia inválida.')

            if not tipo:
                row_err.setdefault('tipo', []).append('Tipo requerido.')
            elif allowed_tipos is not None and tipo not in allowed_tipos:
                row_err.setdefault('tipo', []).append('Tipo inválido.')

            if not calif:
                row_err.setdefault('calificacion', []).append('Calificación requerida.')
            else:
                # normalizar: "No entregado" -> "NO ENTREGADO"; también TEA/TEP/TED
                calif_up = calif.upper()
                if calif_up == 'NO ENTREGADO':
                    calif = 'NO ENTREGADO'
                else:
                    # correr el validador legacy del modelo
                    try:
                        # validate_calificacion_ext vive en models.py
                        from .models import validate_calificacion_ext
                        validate_calificacion_ext(calif_up)
                        calif = calif_up
                    except ValidationError as ve:
                        row_err.setdefault('calificacion', []).append(str(ve))
                    except Exception:
                        # fallback: si algo raro pasa, no rompemos, pero marcamos error
                        row_err.setdefault('calificacion', []).append('Calificación inválida.')

            try:
                cuatri = int(cuatri_raw)
                if cuatri not in (1, 2):
                    raise ValueError()
            except Exception:
                row_err.setdefault('cuatrimestre', []).append('El cuatrimestre debe ser 1 o 2.')
                cuatri = None

            fecha = None
            if fecha_raw in (None, ''):
                fecha = today
            else:
                try:
                    # soporta YYYY-MM-DD
                    fecha = parse_date(str(fecha_raw).strip())
                    if not fecha:
                        raise ValueError('fecha inválida')
                except Exception:
                    row_err.setdefault('fecha', []).append('fecha inválida (formato YYYY-MM-DD).')

            if row_err:
                errors.append({"index": idx, "errors": row_err})
                continue

            notas_objs.append(
                Nota(
                    alumno=alumno,
                    materia=materia,
                    tipo=tipo,
                    calificacion=calif,
                    cuatrimestre=cuatri,
                    fecha=fecha,
                )
            )

        if not notas_objs:
            return Response(
                {"ok": False, "created": [], "errors": errors, "notificados": 0},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ------------------------
        # 3) Guardar (bulk) + Notificaciones (bulk, sin N queries)
        # ------------------------
        created_ids = []
        notificados = 0

        # prefetch de users por legajo (1 query)
        User = get_user_model()
        legajos = []
        for n in notas_objs:
            try:
                leg = (getattr(n.alumno, 'id_alumno', '') or '').strip()
                if leg:
                    legajos.append(leg)
            except Exception:
                pass
        legajos = sorted(set(legajos))

        users_by_username_lower = {}
        if legajos:
            qs_u = User.objects.filter(
                Q(username__in=legajos) | Q(username__in=[x.upper() for x in legajos]) | Q(username__in=[x.lower() for x in legajos])
            ).only('id', 'username')
            for u in qs_u:
                try:
                    users_by_username_lower[(u.username or '').lower()] = u
                except Exception:
                    pass

        def _destinatarios_para_alumno(a: Alumno):
            destinatarios = []
            seen = set()

            def _add(u):
                if u is None:
                    return
                uid = getattr(u, 'id', None)
                if uid is None or uid in seen:
                    return
                seen.add(uid)
                destinatarios.append(u)

            # padre
            _add(getattr(a, 'padre', None))
            # usuario directo
            _add(getattr(a, 'usuario', None))
            # username==legajo
            try:
                leg = (getattr(a, 'id_alumno', '') or '').strip().lower()
                if leg:
                    _add(users_by_username_lower.get(leg))
            except Exception:
                pass

            return destinatarios

        docente = (request.user.get_full_name() or request.user.username).strip()

        with transaction.atomic():
            Nota.objects.bulk_create(notas_objs, batch_size=500)
            created_ids = [getattr(n, 'id', None) for n in notas_objs if getattr(n, 'id', None) is not None]

            # Agrupar para 1 notificación por (destinatario, alumno)
            grupos = {}
            for n in notas_objs:
                a = n.alumno
                dests = _destinatarios_para_alumno(a)
                if not dests:
                    continue
                for d in dests:
                    key = (getattr(d, 'id', None), getattr(a, 'id', None))
                    if key not in grupos:
                        grupos[key] = {"dest": d, "alumno": a, "curso": getattr(a, 'curso', '') or '', "notas": []}
                    grupos[key]["notas"].append(n)

            notifs = []
            for g in grupos.values():
                a = g['alumno']
                alumno_full = _alumno_nombre(a)
                curso = g['curso']
                notas_alumno = g['notas']

                titulo = (f"Nuevas notas para {alumno_full}" if len(notas_alumno) > 1 else f"Nueva nota para {alumno_full}")

                # lines compactas
                lines = []
                for nn in notas_alumno:
                    f = getattr(nn, 'fecha', None)
                    fstr = f.isoformat() if hasattr(f, 'isoformat') else ''
                    base = f"• {getattr(nn, 'materia', '')} ({getattr(nn, 'tipo', '')}): {getattr(nn, 'calificacion', '')}".strip()
                    if fstr:
                        base += f" — {fstr}"
                    lines.append(base)

                descripcion = (
                    "Se registraron nuevas calificaciones. "
                    f"Alumno: {alumno_full}. "
                    + (f"Curso: {curso}. " if curso else "")
                    + (" ".join(lines) if lines else "")
                    + (f" Docente: {docente}" if docente else "")
                ).strip()

                notifs.append(
                    Notificacion(
                        destinatario=g['dest'],
                        tipo='nota',
                        titulo=titulo,
                        descripcion=descripcion,
                        url=f"/alumnos/{getattr(a, 'id', '')}/?tab=notas",
                        leida=False,
                        meta={
                            "alumno_id": getattr(a, 'id', None),
                            "nota_ids": [getattr(x, 'id', None) for x in notas_alumno],
                            "curso": curso or "",
                            "docente": docente,
                        },
                    )
                )

            if notifs:
                Notificacion.objects.bulk_create(notifs, batch_size=500)
                notificados = len(notifs)

        # 207 si hubo errores parciales, 201 si todo ok
        if errors:
            return Response(
                {"ok": True, "created": created_ids, "errors": errors, "notificados": notificados},
                status=207,
            )

        return Response({"ok": True, "created": created_ids, "notificados": notificados}, status=status.HTTP_201_CREATED)
