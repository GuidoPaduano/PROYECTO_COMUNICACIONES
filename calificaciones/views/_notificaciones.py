# calificaciones/views/_notificaciones.py
# Notificaciones por NOTA (campanita: Notificacion del sistema)

from django.contrib.auth import get_user_model
from django.utils import timezone

from ..models import Notificacion
from ..utils_cursos import get_course_label


def _resolver_destinatario_padre(alumno):
    """Destinatario para notificación.

    Preferencia: Alumno.padre (FK real)
    Fallback por username==id_alumno
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

    # Último intento: resolver destinatario por legajo
    if not destinatarios:
        try:
            u_fb, _src = _resolver_destinatario_padre(alumno)
            _add(u_fb)
        except Exception:
            pass

    return destinatarios


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
        course_name = _notification_course_name(alumno=alumno, course_code=curso)
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
        if course_name:
            parts.append(f"Curso: {course_name}")
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
                school=getattr(alumno, "school", None),
                destinatario=destinatario,
                tipo="nota",
                titulo=titulo,
                descripcion=descripcion,
                url=url,
                meta={
                    "alumno_id": alumno.id,
                    "nota_id": getattr(nota, "id", None),
                    **_notification_course_meta(alumno=alumno, course_code=curso),
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
            course_name = _notification_course_name(alumno=alumno, course_code=curso)
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
            if course_name:
                descripcion += f" Curso: {course_name}."
            if lines:
                # Guardamos en texto (la UI lo truncará si hace falta)
                descripcion += " " + " ".join(lines)

            url = f"/alumnos/{alumno.id}/?tab=notas"

            notifs.append(
                Notificacion(
                    school=getattr(alumno, "school", None),
                    destinatario=g["dest"],
                    tipo="nota",
                    titulo=titulo,
                    descripcion=descripcion,
                    url=url,
                    meta={
                        "alumno_id": alumno.id,
                        "nota_ids": [getattr(x, "id", None) for x in notas_alumno],
                        **_notification_course_meta(alumno=alumno, course_code=curso),
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
