# calificaciones/api_nueva_nota/_helpers.py
from decimal import Decimal, InvalidOperation
import unicodedata

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q

from ..course_access import (
    assignment_matches_course,
    build_course_membership_q,
    course_ref_matches,
    filter_course_options_by_refs,
    get_assignment_course_refs,
)
from ..models import Alumno, Nota, resolve_school_course_for_value
from ..schools import scope_queryset_to_school
from ..utils_cursos import get_course_label, get_school_course_dicts

# ---------- Catálogo (con fallbacks) ----------
try:
    from ..constants import MATERIAS as MATERIAS_CATALOGO
except Exception:
    MATERIAS_CATALOGO = None

try:
    from ..models_preceptores import ProfesorCurso  # type: ignore
except Exception:
    ProfesorCurso = None

try:
    from ..models_preceptores import PreceptorCurso  # type: ignore
except Exception:
    PreceptorCurso = None


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
        "Ăˇ": "a",
        "Ă©": "e",
        "Ă­": "i",
        "Ăł": "o",
        "Ăş": "u",
        "Ă": "A",
        "Ă‰": "E",
        "Ă": "I",
        "Ă“": "O",
        "Ăš": "U",
        "Ă±": "n",
        "Ă‘": "N",
        "ĂĽ": "u",
        "Ăś": "U",
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


def _cursos_preceptor_asignados_refs(user, school=None):
    if PreceptorCurso is None:
        return []
    try:
        qs = PreceptorCurso.objects.filter(preceptor=user)
        if school is not None:
            qs = scope_queryset_to_school(qs, school)
        return get_assignment_course_refs(qs)
    except Exception:
        return []


def _filtrar_cursos_para_profesor(user, cursos, school=None):
    if getattr(user, "is_superuser", False):
        return cursos
    if _is_directivo_user(user):
        return cursos
    if _has_group(user, "Preceptores", "Preceptor"):
        refs = _cursos_preceptor_asignados_refs(user, school=school)
        if not refs:
            return []
        return filter_course_options_by_refs(cursos, refs)
    if _is_profesor_user(user):
        refs = _cursos_profesor_asignados_refs(user, school=school)
        if not refs:
            return []
        return filter_course_options_by_refs(cursos, refs)
    return cursos


def _profesor_puede_editar_nota(user, nota) -> bool:
    alumno = getattr(nota, "alumno", None)
    if alumno is None:
        return False
    return _usuario_puede_operar_nota_en_alumno(user, alumno)


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

    # Último intento si no hubo destinatarios
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


def _notify_padre_nota(remitente, nota):
    from ..models import Notificacion
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
