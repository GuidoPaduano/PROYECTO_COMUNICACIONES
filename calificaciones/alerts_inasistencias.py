from __future__ import annotations

from decimal import Decimal
from collections import defaultdict
from typing import Any

from django.conf import settings
from django.utils import timezone

from .course_access import (
    build_course_lookup_keys,
    build_course_lookup_keys_for_refs,
    build_assignment_course_q_for_refs,
    build_course_ref,
    filter_assignments_for_course,
    get_object_course_lookup_keys,
)
from .models import AlertaInasistencia, Asistencia, Notificacion

try:
    from .models_preceptores import PreceptorCurso  # type: ignore
except Exception:
    PreceptorCurso = None


def _cfg_int(name: str, default: int) -> int:
    try:
        return int(getattr(settings, name, default))
    except Exception:
        return default


def _cfg_umbral_faltas() -> list[int]:
    raw = str(getattr(settings, "ALERTAS_INASISTENCIAS_UMBRALES_FALTAS", "10,20,25") or "").strip()
    if not raw:
        return [10, 20, 25]
    out = []
    for p in raw.split(","):
        s = p.strip()
        if not s:
            continue
        try:
            v = int(s)
        except Exception:
            continue
        if v > 0:
            out.append(v)
    if not out:
        out = [10, 20, 25]
    return sorted(set(out))


def _alumno_nombre(alumno) -> str:
    nm = (getattr(alumno, "nombre", "") or "").strip()
    ap = (getattr(alumno, "apellido", "") or "").strip()
    full = f"{nm} {ap}".strip()
    return full or (getattr(alumno, "id_alumno", "") or "Alumno")


def _course_display(alumno) -> str:
    school_course = getattr(alumno, "school_course", None)
    return (
        getattr(school_course, "name", None)
        or getattr(school_course, "code", None)
        or getattr(alumno, "curso", "")
        or "s/d"
    )


def _course_meta(alumno) -> dict[str, Any]:
    return {
        "school_course_id": getattr(alumno, "school_course_id", None),
        "school_course_name": _course_display(alumno),
    }


def _assignment_lookup_keys(assignment) -> list[tuple[int | None, int | None, str]]:
    keys = build_course_lookup_keys(
        school_id=getattr(assignment, "school_id", None),
        school_course_id=getattr(assignment, "school_course_id", None),
        course_code=getattr(getattr(assignment, "school_course", None), "code", None) or getattr(assignment, "curso", "") or "",
    )
    if getattr(assignment, "school_id", None) is not None or getattr(assignment, "school_course_id", None) is not None:
        keys = [key for key in keys if not (key[0] is None and key[1] is None)]
    return keys


def _destinatarios(
    alumno,
    *,
    preceptores_por_curso: dict[tuple[int | None, int | None, str], list[Any]] | None = None,
):
    out = []
    seen = set()

    def _add(user):
        if user is None:
            return
        uid = getattr(user, "id", None)
        if uid is None or uid in seen:
            return
        seen.add(uid)
        out.append(user)

    _add(getattr(alumno, "padre", None))

    if preceptores_por_curso is not None:
        for key in get_object_course_lookup_keys(alumno):
            for p in preceptores_por_curso.get(key, []):
                _add(p)
        return out

    if PreceptorCurso is not None:
        try:
            qs = filter_assignments_for_course(
                PreceptorCurso.objects.select_related("preceptor"),
                obj=alumno,
            )
            for pc in qs:
                _add(getattr(pc, "preceptor", None))
        except Exception:
            pass
    return out


def _consecutivas_no_justificadas(*, alumno, tipo_asistencia: str) -> tuple[int, list[str]]:
    qs = (
        Asistencia.objects.filter(alumno=alumno, tipo_asistencia=tipo_asistencia)
        .order_by("-fecha", "-id")
    )
    count = 0
    fechas = []
    for a in qs:
        ausente_no_just = (not bool(getattr(a, "presente", True))) and (not bool(getattr(a, "justificada", False)))
        if ausente_no_just:
            count += 1
            try:
                fechas.append(a.fecha.isoformat())
            except Exception:
                pass
        else:
            break
    return count, fechas


def _crear_notificaciones(
    *,
    alerta: AlertaInasistencia,
    consecutivas: int,
    umbral: int,
    preceptores_por_curso: dict[tuple[int | None, int | None, str], list[Any]] | None = None,
):
    alumno = alerta.alumno
    destinatarios = _destinatarios(alumno, preceptores_por_curso=preceptores_por_curso)
    if not destinatarios:
        return 0

    alumno_nombre = _alumno_nombre(alumno)
    course_name = _course_display(alumno)
    titulo = f"{alumno_nombre} necesita atencion por inasistencias"
    descripcion = (
        f"Se detectaron {consecutivas} ausencias consecutivas no justificadas. "
        f"Curso: {course_name}."
    )

    notifs = []
    school_ref = getattr(alerta, "school", None) or getattr(alumno, "school", None)
    for d in destinatarios:
        notifs.append(
            Notificacion(
                school=school_ref,
                destinatario=d,
                tipo="inasistencia",
                titulo=titulo,
                descripcion=descripcion,
                url=f"/alumnos/{getattr(alumno, 'id', '')}?tab=asistencias",
                leida=False,
                meta={
                    "es_alerta_inasistencia": True,
                    "alerta_inasistencia_id": alerta.id,
                    "alumno_id": getattr(alumno, "id", None),
                    "alumno_legajo": getattr(alumno, "id_alumno", None),
                    **_course_meta(alumno),
                    "motivo": alerta.motivo,
                    "valor_actual": consecutivas,
                    "umbral": umbral,
                },
            )
        )
    Notificacion.objects.bulk_create(notifs, batch_size=200)
    return len(notifs)


def _total_faltas_clases(*, alumno, tipo_asistencia: str) -> int:
    try:
        return int(
            Asistencia.objects.filter(
                alumno=alumno,
                tipo_asistencia=tipo_asistencia,
                presente=False,
            ).count()
        )
    except Exception:
        return 0


def _crear_alertas_faltas_acumuladas(
    *,
    alumno,
    tipo_asistencia: str,
    actor=None,
    asistencia=None,
    preceptores_por_curso: dict[tuple[int | None, int | None, str], list[Any]] | None = None,
) -> int:
    total = _total_faltas_clases(alumno=alumno, tipo_asistencia=tipo_asistencia)
    if total <= 0:
        return 0

    created = 0
    for umbral in _cfg_umbral_faltas():
        if total < umbral:
            continue
        exists = AlertaInasistencia.objects.filter(
            alumno=alumno,
            tipo_asistencia=tipo_asistencia,
            motivo="FALTAS_ACUMULADAS",
            umbral=Decimal(str(umbral)),
        ).exists()
        if exists:
            continue

        alerta = AlertaInasistencia.objects.create(
            school=getattr(alumno, "school", None) or getattr(asistencia, "school", None),
            alumno=alumno,
            school_course=getattr(alumno, "school_course", None),
            curso=getattr(alumno, "curso", "") or "",
            tipo_asistencia=tipo_asistencia,
            motivo="FALTAS_ACUMULADAS",
            severidad=1,
            valor_actual=Decimal(str(total)),
            umbral=Decimal(str(umbral)),
            estado="activa",
            fecha_evento=timezone.localdate(),
            detalle={"total_faltas_clases": total},
            asistencia_disparadora=asistencia,
            creada_por=actor,
        )

        destinatarios = _destinatarios(alumno, preceptores_por_curso=preceptores_por_curso)
        if destinatarios:
            alumno_nombre = _alumno_nombre(alumno)
            course_name = _course_display(alumno)
            titulo = f"{alumno_nombre} necesita atencion por inasistencias"
            descripcion = (
                f"El alumno alcanzo {total} inasistencias totales a clases. "
                f"Curso: {course_name}."
            )
            notifs = []
            for d in destinatarios:
                notifs.append(
                    Notificacion(
                        school=getattr(alerta, "school", None) or getattr(alumno, "school", None),
                        destinatario=d,
                        tipo="inasistencia",
                        titulo=titulo,
                        descripcion=descripcion,
                        url=f"/alumnos/{getattr(alumno, 'id', '')}?tab=asistencias",
                        leida=False,
                        meta={
                            "es_alerta_inasistencia": True,
                            "alerta_inasistencia_id": alerta.id,
                            "alumno_id": getattr(alumno, "id", None),
                            "alumno_legajo": getattr(alumno, "id_alumno", None),
                            **_course_meta(alumno),
                            "motivo": alerta.motivo,
                            "valor_actual": total,
                            "umbral": umbral,
                        },
                    )
                )
            Notificacion.objects.bulk_create(notifs, batch_size=200)
        created += 1
    return created


def evaluar_alerta_inasistencia(
    *,
    alumno,
    tipo_asistencia: str = "clases",
    actor=None,
    asistencia=None,
    preceptores_por_curso: dict[tuple[int | None, int | None, str], list[Any]] | None = None,
) -> dict[str, Any]:
    if not alumno:
        return {"created": False, "reason": "no_alumno"}

    umbral = _cfg_int("ALERTAS_INASISTENCIAS_CONSECUTIVAS", 2)
    cooldown = _cfg_int("ALERTAS_INASISTENCIAS_COOLDOWN_DIAS", 7)
    reapertura = _cfg_int("ALERTAS_INASISTENCIAS_REAPERTURA_DIAS", 14)
    hoy = timezone.localdate()

    consecutivas, fechas = _consecutivas_no_justificadas(alumno=alumno, tipo_asistencia=tipo_asistencia)

    acumuladas_creadas = _crear_alertas_faltas_acumuladas(
        alumno=alumno,
        tipo_asistencia=tipo_asistencia,
        actor=actor,
        asistencia=asistencia,
        preceptores_por_curso=preceptores_por_curso,
    )

    if consecutivas < umbral:
        abiertas = AlertaInasistencia.objects.filter(
            alumno=alumno,
            tipo_asistencia=tipo_asistencia,
            motivo="AUSENCIAS_CONSECUTIVAS",
            estado="activa",
        )
        cerradas = abiertas.update(estado="cerrada", cerrada_en=timezone.now())
        return {
            "created": bool(acumuladas_creadas),
            "reason": "below_threshold",
            "closed": int(cerradas),
            "valor_actual": consecutivas,
            "acumuladas_creadas": int(acumuladas_creadas),
        }

    ultima = (
        AlertaInasistencia.objects.filter(
            alumno=alumno,
            tipo_asistencia=tipo_asistencia,
            motivo="AUSENCIAS_CONSECUTIVAS",
        )
        .order_by("-creada_en", "-id")
        .first()
    )
    if ultima is not None:
        dias = (hoy - (getattr(ultima, "fecha_evento", hoy) or hoy)).days
        if dias < cooldown:
            return {"created": bool(acumuladas_creadas), "reason": "cooldown", "valor_actual": consecutivas, "acumuladas_creadas": int(acumuladas_creadas)}
        if dias < reapertura:
            return {"created": bool(acumuladas_creadas), "reason": "reapertura", "valor_actual": consecutivas, "acumuladas_creadas": int(acumuladas_creadas)}

    alerta = AlertaInasistencia.objects.create(
        school=getattr(alumno, "school", None) or getattr(asistencia, "school", None),
        alumno=alumno,
        school_course=getattr(alumno, "school_course", None),
        curso=getattr(alumno, "curso", "") or "",
        tipo_asistencia=tipo_asistencia,
        motivo="AUSENCIAS_CONSECUTIVAS",
        severidad=1,
        valor_actual=Decimal(str(consecutivas)),
        umbral=Decimal(str(umbral)),
        estado="activa",
        fecha_evento=hoy,
        detalle={"fechas_consecutivas": fechas},
        asistencia_disparadora=asistencia,
        creada_por=actor,
    )

    notifs = _crear_notificaciones(
        alerta=alerta,
        consecutivas=consecutivas,
        umbral=umbral,
        preceptores_por_curso=preceptores_por_curso,
    )
    return {
        "created": True,
        "alerta_id": alerta.id,
        "valor_actual": consecutivas,
        "umbral": umbral,
        "notificaciones": notifs,
        "acumuladas_creadas": int(acumuladas_creadas),
    }


def evaluar_alertas_inasistencia_por_alumnos(*, alumno_ids: list[int], tipo_asistencia: str = "clases", actor=None) -> int:
    if not alumno_ids:
        return 0
    created = 0
    qs = Asistencia.objects.filter(alumno_id__in=alumno_ids).select_related("alumno").order_by("-fecha", "-id")
    by_alumno = {}
    for a in qs:
        aid = getattr(a, "alumno_id", None)
        if aid is None or aid in by_alumno:
            continue
        by_alumno[aid] = a

    preceptores_por_curso: dict[tuple[int | None, int | None, str], list[Any]] = {}
    if PreceptorCurso is not None:
        try:
            refs = [
                build_course_ref(obj=getattr(a, "alumno", None))
                for a in by_alumno.values()
                if getattr(a, "alumno", None) is not None
            ]
            keys = set(build_course_lookup_keys_for_refs(refs))
            if keys:
                qs = PreceptorCurso.objects.select_related("preceptor", "school_course")
                query = build_assignment_course_q_for_refs(refs)
                if query is not None:
                    qs = qs.filter(query)
                else:
                    qs = qs.none()

                tmp: dict[tuple[int | None, int | None, str], list[Any]] = defaultdict(list)
                seen: dict[tuple[int | None, int | None, str], set[int]] = defaultdict(set)
                for pc in qs:
                    p = getattr(pc, "preceptor", None)
                    pid = getattr(p, "id", None)
                    if p is None or pid is None:
                        continue
                    for key in _assignment_lookup_keys(pc):
                        if key not in keys or pid in seen[key]:
                            continue
                        seen[key].add(pid)
                        tmp[key].append(p)
                preceptores_por_curso = dict(tmp)
        except Exception:
            preceptores_por_curso = {}

    for aid in sorted(set(alumno_ids)):
        a = by_alumno.get(aid)
        alumno = getattr(a, "alumno", None) if a else None
        if alumno is None:
            continue
        info = evaluar_alerta_inasistencia(
            alumno=alumno,
            tipo_asistencia=tipo_asistencia,
            actor=actor,
            asistencia=a,
            preceptores_por_curso=preceptores_por_curso,
        )
        if info.get("created"):
            created += 1
    return created
