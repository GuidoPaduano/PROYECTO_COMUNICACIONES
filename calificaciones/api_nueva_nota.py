# calificaciones/api_nueva_nota.py
from decimal import Decimal, InvalidOperation
import logging
import unicodedata

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

from .course_access import (
    assignment_matches_course,
    build_course_membership_q,
    build_course_membership_q_for_refs,
    course_ref_matches,
    filter_course_options_by_refs,
    get_assignment_course_refs,
)
from .models import Alumno, Nota, Mensaje, Notificacion, resolve_school_course_for_value
from .serializers import AlumnoSerializer, NotaCreateSerializer
from .contexto import build_context_for_user, alumno_to_dict
from .schools import (
    get_available_school_dicts_for_user,
    get_request_school,
    get_requested_school_identifier,
    get_school_by_identifier,
    school_to_dict,
    scope_queryset_to_school,
    user_can_access_school,
)
from .utils_cursos import get_school_course_dicts, resolve_course_reference
from .alerts import evaluar_alerta_nota
from .user_groups import get_user_group_names

logger = logging.getLogger(__name__)

# ---------- Catálogo (con fallbacks) ----------
try:
    from .constants import MATERIAS as MATERIAS_CATALOGO
except Exception:
    MATERIAS_CATALOGO = None

try:
    from .models_preceptores import ProfesorCurso  # type: ignore
except Exception:
    ProfesorCurso = None


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


def _resultados_catalogo():
    return [{"id": key, "label": label} for key, label in Nota.RESULTADO_CHOICES]


def _calificaciones_texto_catalogo():
    return ["TEA", "TEP", "TED", "NO ENTREGADO"] + [str(x) for x in range(1, 11)]


def _parse_decimal_optional(value):
    if value in (None, ""):
        return None
    try:
        parsed = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if parsed < Decimal("1") or parsed > Decimal("10"):
        return None
    return parsed.quantize(Decimal("0.01"))


def _filter_alumnos_por_curso(qs, curso: str, *, school=None):
    curso = (curso or "").strip()
    if not curso:
        return qs

    school_course = resolve_school_course_for_value(school=school, curso=curso) if school is not None else None
    course_q = build_course_membership_q(
        school_course_id=getattr(school_course, "id", None),
        course_code=curso,
        school_course_field="school_course",
        code_field="curso",
    )
    if course_q is None:
        return qs.none()
    return qs.filter(course_q)


def _normalize_catalog_text(value):
    text = str(value or "").strip()
    if not text:
        return ""

    replacements = {
        "Ã¡": "a",
        "Ã©": "e",
        "Ã­": "i",
        "Ã³": "o",
        "Ãº": "u",
        "Ã": "A",
        "Ã‰": "E",
        "Ã": "I",
        "Ã“": "O",
        "Ãš": "U",
        "Ã±": "n",
        "Ã‘": "N",
        "Ã¼": "u",
        "Ãœ": "U",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)

    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(normalized.upper().split())


def _build_choice_alias_map(*choice_groups):
    alias_map = {}
    for group in choice_groups:
        for item in group or []:
            if isinstance(item, (list, tuple)) and item:
                raw_value = item[0]
            else:
                raw_value = item

            value = str(raw_value or "").strip()
            if not value:
                continue
            alias_map.setdefault(_normalize_catalog_text(value), value)
    return alias_map


def get_materias_catalogo():
    return list(MATERIAS_CATALOGO) if MATERIAS_CATALOGO else _materias_por_defecto()


def _cursos_catalogo(school=None):
    """Devuelve cursos del colegio con school_course_id como referencia principal y code legible para UI."""
    cursos = []
    for item in get_school_course_dicts(
        school=school,
        fallback_to_defaults=False,
        catalog_only=True,
    ):
        code = str(item.get("id") or item.get("code") or "").strip()
        if not code:
            continue
        school_course_id = item.get("school_course_id")
        if school_course_id is None and school is not None:
            school_course = resolve_school_course_for_value(school=school, curso=code)
            school_course_id = getattr(school_course, "id", None)
        cursos.append(
            {
                "id": code,
                "code": code,
                "nombre": str(item.get("nombre") or code),
                "school_course_id": school_course_id,
            }
        )
    return cursos


def _cursos_profesor_asignados(user, school=None):
    refs = _cursos_profesor_asignados_refs(user, school=school)
    if not refs:
        return []
    out = []
    for course in _cursos_catalogo(school=school):
        code = str(course.get("code") or course.get("id") or "").strip()
        if not code:
            continue
        if course_ref_matches(
            refs,
            school=school,
            school_course_id=course.get("school_course_id"),
            course_code=code,
        ):
            out.append(code)
    return out


def _profesor_assignment_qs(user, school=None):
    if ProfesorCurso is None:
        return None
    try:
        qs = ProfesorCurso.objects.filter(profesor=user)
        return scope_queryset_to_school(qs, school)
    except Exception:
        return None


def _cursos_profesor_asignados_refs(user, school=None):
    qs = _profesor_assignment_qs(user, school=school)
    if qs is None:
        return []
    try:
        return get_assignment_course_refs(qs)
    except Exception:
        return []


def _has_group(user, *names):
    try:
        return user.groups.filter(name__in=list(names)).exists()
    except Exception:
        return False


def _is_profesor_user(user) -> bool:
    return _has_group(user, "Profesores", "Profesor")


def _is_directivo_user(user) -> bool:
    return _has_group(user, "Directivos", "Directivo")


def _usuario_puede_operar_nota_en_alumno(user, alumno: Alumno) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    if _is_directivo_user(user):
        return True
    if not _is_profesor_user(user):
        return False

    qs = _profesor_assignment_qs(user, school=getattr(alumno, "school", None))
    if qs is None:
        return False
    return assignment_matches_course(qs, obj=alumno)


def _filtrar_cursos_para_profesor(user, cursos, school=None):
    if not _is_profesor_user(user):
        return cursos

    refs = _cursos_profesor_asignados_refs(user, school=school)
    if not refs:
        return []
    return filter_course_options_by_refs(cursos, refs)


def _profesor_puede_editar_nota(user, nota: Nota) -> bool:
    alumno = getattr(nota, "alumno", None)
    if alumno is None:
        return False
    return _usuario_puede_operar_nota_en_alumno(user, alumno)


# ---------- WhoAmI ----------
class WhoAmI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        u = request.user
        groups = list(get_user_group_names(u))
        requested_school_identifier = get_requested_school_identifier(request)
        if requested_school_identifier and not getattr(u, "is_superuser", False):
            requested_school = get_school_by_identifier(requested_school_identifier)
            if requested_school is None:
                return Response({"detail": "Colegio no encontrado."}, status=status.HTTP_404_NOT_FOUND)
            if not user_can_access_school(u, requested_school):
                return Response(
                    {"detail": "El usuario no pertenece al colegio seleccionado."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        active_school = get_request_school(request)

        # Vista previa de rol para superusuario (respeta X-Preview-Role / ?view_as=)
        try:
            from .views import _get_preview_role
            preview_role = _get_preview_role(request)
        except Exception:
            preview_role = None
        if preview_role and getattr(u, "is_superuser", False):
            groups = [preview_role]

        full_name = (u.get_full_name() or f"{u.first_name} {u.last_name}").strip()

        # Contexto de usuario (resolucion tolerante) para que el front pueda
        # resolver "quién es el alumno" sin depender de vínculos frágiles.
        try:
            ctx = build_context_for_user(u, groups, school=active_school)
        except Exception:
            logger.exception(
                "WhoAmI: error construyendo contexto para user_id=%s",
                getattr(u, "id", None),
            )
            ctx = {}

        # Vista previa (superusuario): si simula un rol y no hay contexto real, proveo un fallback razonable.
        if preview_role and getattr(u, "is_superuser", False) and active_school is not None:
            try:
                if "Alumnos" in groups and not ctx.get("alumno"):
                    a0 = scope_queryset_to_school(Alumno.objects.all(), active_school).order_by("id").first()
                    ctx["alumno"] = alumno_to_dict(a0)
            except Exception:
                pass

        # `alumno` va arriba porque el front actual lo consume asi.
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
                "school": school_to_dict(active_school),
                "available_schools": get_available_school_dicts_for_user(u, active_school=active_school),
                **ctx,
            },
            status=status.HTTP_200_OK,
        )


# ---------- Datos iniciales para “Nueva Nota” ----------
class NuevaNotaDatosIniciales(APIView):
    """
    GET /api/calificaciones/nueva-nota/datos/?school_course_id=14
    Usa school_course_id para filtrar por curso.
    Devuelve alumnos (opcionalmente filtrados por curso),
    catálogo de materias, tipos y cuatrimestres.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        active_school = get_request_school(request)
        school_course, curso, course_error = resolve_course_reference(
            school=active_school,
            raw_course=request.query_params.get("curso"),
            raw_school_course_id=request.query_params.get("school_course_id"),
            required=False,
        )
        if course_error:
            return Response({"detail": course_error}, status=status.HTTP_400_BAD_REQUEST)
        assigned_course_refs = []
        try:
            if _is_profesor_user(request.user):
                assigned_course_refs = _cursos_profesor_asignados_refs(request.user, school=active_school)
        except Exception:
            assigned_course_refs = []

        if (school_course is not None or curso) and assigned_course_refs and not course_ref_matches(
            assigned_course_refs,
            school_course_id=getattr(school_course, "id", None),
            course_code=curso,
        ):
            return Response({"detail": "No tenés permiso para ese curso."}, status=status.HTTP_403_FORBIDDEN)

        cursos_catalogo = _filtrar_cursos_para_profesor(
            request.user,
            _cursos_catalogo(school=active_school),
            school=active_school,
        )
        selected_course = None
        if school_course is not None:
            selected_course = next(
                (c for c in cursos_catalogo if c.get("school_course_id") == getattr(school_course, "id", None)),
                None,
            )
        if selected_course is None and curso:
            selected_course = next(
                (c for c in cursos_catalogo if str(c.get("code") or c.get("id") or "").strip() == curso),
                None,
            )
        if selected_course is None and cursos_catalogo:
            selected_course = cursos_catalogo[0]

        school_course_id_inicial = None
        school_course_name_inicial = ""
        selected_course_code = ""
        if selected_course is not None:
            selected_course_code = str(selected_course.get("code") or selected_course.get("id") or "").strip()
            school_course_id_inicial = selected_course.get("school_course_id")
            school_course_name_inicial = str(selected_course.get("nombre") or "").strip()

        alumnos_qs = scope_queryset_to_school(
            Alumno.objects.only("id", "id_alumno", "nombre", "apellido", "curso"),
            active_school,
        ).order_by("nombre")
        if selected_course_code:
            alumnos_qs = _filter_alumnos_por_curso(alumnos_qs, selected_course_code, school=active_school)
        elif assigned_course_refs:
            allowed_course_q = build_course_membership_q_for_refs(
                assigned_course_refs,
                school_course_field="school_course",
                code_field="curso",
            )
            alumnos_qs = alumnos_qs.filter(allowed_course_q) if allowed_course_q is not None else alumnos_qs.none()

        data = {
            "alumnos": AlumnoSerializer(alumnos_qs, many=True).data,
            "cursos": cursos_catalogo,
            "school_course_id_inicial": school_course_id_inicial,
            "school_course_name_inicial": school_course_name_inicial,
            "materias": get_materias_catalogo(),
            "tipos": _tipos_por_defecto(),
            "cuatrimestres": _cuatris_por_defecto(),
            "resultados": _resultados_catalogo(),
            "calificaciones": _calificaciones_texto_catalogo(),
            "hoy": timezone.localdate(),
        }
        return Response(data, status=status.HTTP_200_OK)

# ---------- Helpers para mapear alumno ----------
def _resolver_alumno_id(valor, school=None):
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
            qs = scope_queryset_to_school(Alumno.objects.all(), school)
            return qs.get(pk=int(sv))
        # si no es dígito intento por id_alumno (legajo)
        qs = scope_queryset_to_school(Alumno.objects.all(), school)
        return qs.get(id_alumno=sv)
    except Alumno.DoesNotExist:
        return None


def _normalizar_nota_payload(d, school=None):
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
    if "nota_numerica" not in data and "notaNumerica" in data:
        data["nota_numerica"] = data.pop("notaNumerica")
    if "resultado" in data and data["resultado"] not in (None, ""):
        data["resultado"] = str(data["resultado"]).strip().upper()
    # Si alumno es legajo o string, lo convierto a pk
    alumno_val = data.get("alumno", None)
    if alumno_val is not None:
        inst = _resolver_alumno_id(alumno_val, school=school)
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
      - 'username==id_alumno' (fallback por username==legajo)
      - None
    """
    padre = getattr(alumno, "padre", None)
    if padre is not None:
        return padre, "alumno.padre"

    # Fallback por username==legajo
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

    # Ultimo intento si no hubo destinatarios
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


def _notification_course_name(*, alumno=None, school_course=None, course_code="", school=None):
    resolved_school_course = school_course or getattr(alumno, "school_course", None)
    return (
        getattr(resolved_school_course, "name", None)
        or getattr(resolved_school_course, "code", None)
        or get_course_label(
            course_code or getattr(alumno, "curso", ""),
            school=school or getattr(alumno, "school", None),
        )
        or course_code
        or getattr(alumno, "curso", None)
        or None
    )


def _notification_course_meta(*, alumno=None, school_course=None, course_code="", school=None):
    return {
        "school_course_id": getattr(school_course, "id", None) or getattr(alumno, "school_course_id", None),
        "school_course_name": _notification_course_name(
            alumno=alumno,
            school_course=school_course,
            course_code=course_code,
            school=school,
        ),
    }


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

        alumno_nombre = _alumno_nombre(alumno)
        curso_alumno = getattr(alumno, "curso", "") or ""
        course_name = _notification_course_name(alumno=alumno, course_code=curso_alumno)

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
            + (f"Curso: {course_name} " if course_name else "")
            + (f"Materia: {materia_nombre} " if materia_nombre else "")
            + (f"Tipo: {tipo} " if tipo else "")
            + (f"Calificación: {calif} " if calif is not None else "")
            + (f"Fecha: {fecha_str} " if fecha_str else "")
            + (f"Docente: {docente_label}" if docente_label else "")
        ).strip()

        notificado = False
        last_id = None
        school_ref = getattr(nota, "school", None) or getattr(alumno, "school", None)

        for destinatario in destinatarios:
            Notificacion.objects.create(
                school=school_ref,
                destinatario=destinatario,
                tipo="nota",
                titulo=asunto_msg,
                descripcion=contenido_msg,
                url=f"/alumnos/{getattr(alumno, 'id', '')}/?tab=notas",
                leida=False,
                meta={
                    "alumno_id": getattr(alumno, "id", None),
                    "alumno_legajo": getattr(alumno, "id_alumno", None),
                    **_notification_course_meta(alumno=alumno, course_code=curso_alumno, school=school_ref),
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
    Body JSON:
    {
      alumno | alumno_id | id_alumno,
      materia,
      tipo,
      resultado?,         # TEA/TEP/TED
      nota_numerica?,     # 1..10
      calificacion?,      # campo heredado
      cuatrimestre,
      fecha?
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        active_school = get_request_school(request)
        payload = _normalizar_nota_payload(request.data, school=active_school)
        serializer = NotaCreateSerializer(data=payload)
        if serializer.is_valid():
            alumno = serializer.validated_data.get("alumno")
            if alumno is None or not _usuario_puede_operar_nota_en_alumno(request.user, alumno):
                return Response(
                    {"detail": "No tenés permiso para cargar notas para ese alumno."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            nota = serializer.save()
            school_ref = getattr(getattr(nota, "alumno", None), "school", None) or active_school
            if school_ref is not None and getattr(nota, "school_id", None) is None:
                nota.school = school_ref
                nota.save(update_fields=["school"])
            notificado, notif_dest_id, notif_source, notif_error = _notify_padre_nota(request.user, nota)
            alerta_info = evaluar_alerta_nota(nota=nota, actor=request.user)
            resp = {"id": nota.id, "notificado": notificado, "notif_destinatario_id": notif_dest_id, "notif_source": notif_source}
            resp["alerta"] = alerta_info
            # Si sos staff/superuser y falló, devolvemos error para debug
            if (not notificado) and notif_error and (
                getattr(request.user, "is_superuser", False) or _is_directivo_user(request.user)
            ):
                resp["notif_error"] = notif_error
            return Response(resp, status=status.HTTP_201_CREATED)
        return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


class EditarNota(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, nota_id, *args, **kwargs):
        active_school = get_request_school(request)
        try:
            nota = scope_queryset_to_school(
                Nota.objects.select_related("alumno"),
                active_school,
            ).get(pk=nota_id)
        except Nota.DoesNotExist:
            return Response({"detail": "Nota no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        if not _profesor_puede_editar_nota(request.user, nota):
            return Response({"detail": "No tenés permiso para editar esta nota."}, status=status.HTTP_403_FORBIDDEN)

        payload = _normalizar_nota_payload(request.data, school=active_school)
        payload["alumno"] = nota.alumno_id

        serializer = NotaCreateSerializer(instance=nota, data=payload, partial=True)
        if not serializer.is_valid():
            return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        nota = serializer.save()
        school_ref = getattr(getattr(nota, "alumno", None), "school", None) or active_school
        if school_ref is not None and getattr(nota, "school_id", None) is None:
            nota.school = school_ref
            nota.save(update_fields=["school"])
        return Response({"nota": NotaCreateSerializer(nota).data}, status=status.HTTP_200_OK)


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
        active_school = get_request_school(request)
        body = request.data
        notas_in = body.get("notas") if isinstance(body, dict) else None
        if not isinstance(notas_in, list):
            return Response(
                {"error": "Formato inválido: se espera {'notas': [ ... ]}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ------------------------
        # 0) Helpers locales
        # ------------------------
        allowed_materias_map = _build_choice_alias_map(
            getattr(Nota, "MATERIAS", []),
            get_materias_catalogo(),
        )
        allowed_tipos_map = _build_choice_alias_map(
            getattr(Nota, "TIPOS", []),
            getattr(Nota, "TIPO_NOTA_CHOICES", []),
            _tipos_por_defecto(),
        )

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

            qs = (
                scope_queryset_to_school(Alumno.objects.filter(q), active_school)
                .select_related("padre", "usuario")
                .only(
                    "id",
                    "id_alumno",
                    "curso",
                    "school",
                    "padre_id",
                    "usuario_id",
                    "nombre",
                    "apellido",
                    "padre__id",
                    "usuario__id",
                )
            )
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
            if not _usuario_puede_operar_nota_en_alumno(request.user, alumno):
                errors.append(
                    {"index": idx, "errors": {"alumno": ["No tenés permiso para cargar notas para ese alumno."]}}
                )
                continue

            materia = (item.get('materia') or '').strip()
            tipo = (item.get('tipo') or '').strip()
            calif_raw = item.get('calificacion')
            calif = str(calif_raw or '').strip().upper()
            resultado = str(item.get('resultado') or '').strip().upper()
            nota_numerica_raw = item.get("nota_numerica", item.get("notaNumerica"))
            nota_numerica = _parse_decimal_optional(nota_numerica_raw)
            cuatri_raw = item.get('cuatrimestre')
            fecha_raw = item.get('fecha', None)

            row_err = {}
            materia_canon = allowed_materias_map.get(_normalize_catalog_text(materia)) if materia else None
            tipo_canon = allowed_tipos_map.get(_normalize_catalog_text(tipo)) if tipo else None

            if not materia:
                row_err.setdefault('materia', []).append('Materia requerida.')
            elif allowed_materias_map and materia_canon is None:
                row_err.setdefault('materia', []).append('Materia invalida.')
            else:
                materia = materia_canon or materia

            if not tipo:
                row_err.setdefault('tipo', []).append('Tipo requerido.')
            elif allowed_tipos_map and tipo_canon is None:
                row_err.setdefault('tipo', []).append('Tipo invalido.')
            else:
                tipo = tipo_canon or tipo

            if resultado and resultado not in {"TEA", "TEP", "TED"}:
                row_err.setdefault("resultado", []).append("Resultado invalido. Usa TEA, TEP o TED.")

            if nota_numerica_raw not in (None, "") and nota_numerica is None:
                row_err.setdefault("nota_numerica", []).append("La nota_numerica debe estar entre 1 y 10.")

            if calif:
                try:
                    from .models import validate_calificacion_ext
                    validate_calificacion_ext(calif)
                except ValidationError as ve:
                    row_err.setdefault('calificacion', []).append(str(ve))
                except Exception:
                    row_err.setdefault('calificacion', []).append('Calificación inválida.')

            if calif and calif in {"TEA", "TEP", "TED"} and not resultado:
                resultado = calif
            if calif and nota_numerica is None:
                parsed_from_calif = _parse_decimal_optional(calif)
                if parsed_from_calif is not None:
                    nota_numerica = parsed_from_calif

            if not calif:
                if resultado:
                    calif = resultado
                elif nota_numerica is not None:
                    calif = str(nota_numerica).rstrip("0").rstrip(".")

            if (not calif) and (not resultado) and (nota_numerica is None):
                row_err.setdefault("resultado", []).append(
                    "Debes informar resultado, nota_numerica o calificacion."
                )

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
                    school=getattr(alumno, "school", None) or active_school,
                    materia=materia,
                    tipo=tipo,
                    calificacion=calif,
                    resultado=(resultado or None),
                    nota_numerica=nota_numerica,
                    cuatrimestre=cuatri,
                    fecha=fecha,
                )
            )

        if not notas_objs:
            return Response(
                {"created": [], "errors": errors, "notificados": 0},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ------------------------
        # 3) Guardar (bulk) + Notificaciones (bulk, sin N queries)
        # ------------------------
        created_ids = []
        notificados = 0
        alertas_creadas = 0

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

        destinatarios_cache = {}

        def _destinatarios_para_alumno(a: Alumno):
            aid = getattr(a, "id", None)
            if aid is not None and aid in destinatarios_cache:
                return destinatarios_cache[aid]

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

            if aid is not None:
                destinatarios_cache[aid] = destinatarios
            return destinatarios

        docente = (request.user.get_full_name() or request.user.username).strip()

        alert_candidates = {}

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
                course_name = _notification_course_name(alumno=a, course_code=curso)
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
                    + (f"Curso: {course_name}. " if course_name else "")
                    + (" ".join(lines) if lines else "")
                    + (f" Docente: {docente}" if docente else "")
                ).strip()

                notifs.append(
                    Notificacion(
                        school=getattr(a, "school", None) or active_school,
                        destinatario=g['dest'],
                        tipo='nota',
                        titulo=titulo,
                        descripcion=descripcion,
                        url=f"/alumnos/{getattr(a, 'id', '')}/?tab=notas",
                        leida=False,
                        meta={
                            "alumno_id": getattr(a, 'id', None),
                            "nota_ids": [getattr(x, 'id', None) for x in notas_alumno],
                            **_notification_course_meta(alumno=a, course_code=curso, school=active_school),
                            "docente": docente,
                        },
                    )
                )

            if notifs:
                Notificacion.objects.bulk_create(notifs, batch_size=500)
                notificados = len(notifs)

            for n in notas_objs:
                key = (
                    getattr(n, "alumno_id", None),
                    getattr(n, "materia", ""),
                    getattr(n, "cuatrimestre", None),
                )
                prev = alert_candidates.get(key)
                if prev is None:
                    alert_candidates[key] = n
                    continue

                prev_fecha = getattr(prev, "fecha", None)
                curr_fecha = getattr(n, "fecha", None)
                prev_id = getattr(prev, "id", 0) or 0
                curr_id = getattr(n, "id", 0) or 0
                if (curr_fecha, curr_id) >= (prev_fecha, prev_id):
                    alert_candidates[key] = n

        if getattr(settings, "ALERTAS_ACADEMICAS_SYNC_EN_CARGA_MASIVA", False):
            for nota_candidata in alert_candidates.values():
                try:
                    info = evaluar_alerta_nota(
                        nota=nota_candidata,
                        actor=request.user,
                        send_email=False,
                    )
                    if info.get("created"):
                        alertas_creadas += 1
                except Exception:
                    pass

        # 207 si hubo errores parciales, 201 si todo ok
        if errors:
            return Response(
                {"created": created_ids, "errors": errors, "notificados": notificados, "alertas": alertas_creadas},
                status=207,
            )

        return Response({"created": created_ids, "notificados": notificados, "alertas": alertas_creadas}, status=status.HTTP_201_CREATED)
