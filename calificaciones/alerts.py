from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.utils import timezone

from .models import AlertaAcademica, Nota, Notificacion
from .resend_email import send_resend_email

try:
    from .models_preceptores import PreceptorCurso  # type: ignore
except Exception:
    PreceptorCurso = None


BAD_RESULTS = {"TEP", "TED"}


def _cfg_int(name: str, default: int) -> int:
    try:
        return int(getattr(settings, name, default))
    except Exception:
        return default


def _cfg_bool(name: str, default: bool = False) -> bool:
    val = getattr(settings, name, default)
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in {"1", "true", "yes", "on"}


def _resultado_principal(nota: Nota) -> str:
    resultado = str(getattr(nota, "resultado", "") or "").strip().upper()
    if resultado in {"TEA", "TEP", "TED"}:
        return resultado

    calif = str(getattr(nota, "calificacion", "") or "").strip().upper()
    if calif in {"TEA", "TEP", "TED", "NO ENTREGADO"}:
        return calif
    return ""


def _riesgo_from_nota(nota: Nota) -> float | None:
    resultado = _resultado_principal(nota)
    if resultado == "TEA":
        return 0.0
    if resultado == "TEP":
        return 0.6
    if resultado == "TED":
        return 1.0
    if resultado == "NO ENTREGADO":
        return 0.8

    nota_numerica = getattr(nota, "nota_numerica", None)
    if nota_numerica is None:
        raw = str(getattr(nota, "calificacion", "") or "").strip().replace(",", ".")
        try:
            nota_numerica = Decimal(raw)
        except Exception:
            nota_numerica = None

    if nota_numerica is None:
        return None

    try:
        value = float(nota_numerica)
    except Exception:
        return None

    if value >= 8:
        return 0.0
    if value >= 6:
        return 0.25
    if value >= 4:
        return 0.6
    if value >= 1:
        return 1.0
    return None


def nota_es_ted(nota: Nota) -> bool:
    return _resultado_principal(nota) == "TED"


def _peso_recencia(fecha, hoy) -> float:
    if not fecha:
        return 0.4
    delta = (hoy - fecha).days
    if delta <= 7:
        return 1.0
    if delta <= 21:
        return 0.7
    return 0.4


def _riesgo_ponderado(notas: list[Nota], hoy) -> tuple[float, int]:
    suma = 0.0
    pesos = 0.0
    n = 0
    for nte in notas:
        riesgo = _riesgo_from_nota(nte)
        if riesgo is None:
            continue
        peso = _peso_recencia(getattr(nte, "fecha", None), hoy)
        suma += riesgo * peso
        pesos += peso
        n += 1
    if pesos <= 0:
        return 0.0, 0
    return (suma / pesos), n


def _trigger_racha(nota: Nota, notas_ventana: list[Nota]) -> bool:
    ultimas_dos = notas_ventana[:2]
    if len(ultimas_dos) < 2:
        return False
    if nota.id not in {getattr(x, "id", None) for x in ultimas_dos}:
        return False
    return all(_resultado_principal(x) in BAD_RESULTS for x in ultimas_dos)


def _trigger_caida_brusca(notas_ventana: list[Nota]) -> bool:
    riesgos = []
    for nte in notas_ventana:
        r = _riesgo_from_nota(nte)
        if r is None:
            continue
        riesgos.append(r)
    if len(riesgos) < 4:
        return False
    ultimas = riesgos[:2]
    anteriores = riesgos[2:4]
    suba = (sum(ultimas) / 2.0) - (sum(anteriores) / 2.0)
    return suba >= 0.35


def _severidad_binaria(*, trigger_a: bool, trigger_b: bool, trigger_c: bool, trigger_d: bool) -> int:
    return 1 if (trigger_a or trigger_b or trigger_c or trigger_d) else 0


def _destinatarios_alerta(alumno):
    destinatarios = []
    seen = set()

    def _add(user):
        if user is None:
            return
        uid = getattr(user, "id", None)
        if uid is None or uid in seen:
            return
        seen.add(uid)
        destinatarios.append(user)

    _add(getattr(alumno, "padre", None))

    if PreceptorCurso is not None:
        try:
            qs = PreceptorCurso.objects.filter(curso=getattr(alumno, "curso", "")).select_related("preceptor")
            for pc in qs:
                _add(getattr(pc, "preceptor", None))
        except Exception:
            pass

    return destinatarios


def _crear_notificaciones_alerta(*, alumno, destinatarios, severidad: int, riesgo: float, trigger_map: dict[str, bool], alerta_id: int):
    if not destinatarios:
        return 0

    alumno_nombre = f"{(getattr(alumno, 'nombre', '') or '').strip()} {(getattr(alumno, 'apellido', '') or '').strip()}".strip()
    if not alumno_nombre:
        alumno_nombre = str(getattr(alumno, "id_alumno", "") or "Alumno")

    triggers_txt = ", ".join(k for k, v in trigger_map.items() if k.startswith(("A_", "B_", "C_", "D_")) and v) or "sin trigger"
    titulo = f"{alumno_nombre} necesita atencion academica"
    descripcion = (
        f"Riesgo academico en {getattr(alumno, 'curso', '') or 'curso sin definir'}"
        f" - Materia: {trigger_map.get('materia', '') or 'N/A'}"
        f" - R={riesgo:.2f}"
        f" - Triggers: {triggers_txt}"
    )

    notifs = []
    for dest in destinatarios:
        notifs.append(
            Notificacion(
                destinatario=dest,
                tipo="otro",
                titulo=titulo,
                descripcion=descripcion,
                url=f"/alumnos/{getattr(alumno, 'id', '')}/?tab=notas",
                leida=False,
                meta={
                    "es_alerta_academica": True,
                    "alerta_id": alerta_id,
                    "alumno_id": getattr(alumno, "id", None),
                    "alumno_legajo": getattr(alumno, "id_alumno", None),
                    "curso": getattr(alumno, "curso", None),
                    "severidad": severidad,
                    "riesgo_ponderado": round(riesgo, 3),
                    "triggers": trigger_map,
                },
            )
        )
    Notificacion.objects.bulk_create(notifs, batch_size=200)
    return len(notifs)


def _enviar_email_alerta(*, alumno, destinatarios, severidad: int, riesgo: float, trigger_map: dict[str, bool]):
    if not _cfg_bool("ALERTAS_ACADEMICAS_EMAIL_ENABLED", False):
        return 0

    enviados = 0
    alumno_nombre = f"{(getattr(alumno, 'nombre', '') or '').strip()} {(getattr(alumno, 'apellido', '') or '').strip()}".strip()
    if not alumno_nombre:
        alumno_nombre = str(getattr(alumno, "id_alumno", "") or "Alumno")

    triggers_txt = ", ".join(k for k, v in trigger_map.items() if k.startswith(("A_", "B_", "C_", "D_")) and v) or "sin trigger"
    subject = f"[Alerta academica] {alumno_nombre}"
    text = (
        f"Alumno: {alumno_nombre}\n"
        f"Curso: {getattr(alumno, 'curso', '')}\n"
        f"Materia: {trigger_map.get('materia', '')}\n"
        f"Riesgo ponderado: {riesgo:.2f}\n"
        f"Triggers: {triggers_txt}\n"
        "Revisa el detalle en el sistema."
    )

    for user in destinatarios:
        to_email = (getattr(user, "email", "") or "").strip()
        if not to_email:
            continue
        ok = send_resend_email(to_email=to_email, subject=subject, text=text)
        if ok:
            enviados += 1
    return enviados


def evaluar_alerta_nota(*, nota: Nota, actor=None) -> dict[str, Any]:
    hoy = timezone.localdate()
    ventana_dias = _cfg_int("ALERTAS_ACADEMICAS_VENTANA_DIAS", 45)
    cooldown_dias = _cfg_int("ALERTAS_ACADEMICAS_COOLDOWN_DIAS", 7)
    escalado_dias = _cfg_int("ALERTAS_ACADEMICAS_ESCALADO_DIAS", 14)
    desde = hoy - timedelta(days=ventana_dias)

    qs = Nota.objects.filter(
        alumno=nota.alumno,
        materia=nota.materia,
        fecha__gte=desde,
        fecha__lte=hoy,
    )
    if getattr(nota, "cuatrimestre", None) in (1, 2):
        qs = qs.filter(cuatrimestre=nota.cuatrimestre)
    notas_ventana = list(qs.order_by("-fecha", "-id"))

    riesgo, n_validas = _riesgo_ponderado(notas_ventana, hoy)
    trigger_a = nota_es_ted(nota)
    trigger_b = _trigger_racha(nota, notas_ventana)
    trigger_c = riesgo >= 0.65 and n_validas >= 3
    trigger_d = _trigger_caida_brusca(notas_ventana)

    if not (trigger_a or trigger_b or trigger_c or trigger_d):
        return {"created": False, "reason": "no_trigger", "riesgo": round(riesgo, 3)}

    severidad = _severidad_binaria(
        trigger_a=trigger_a,
        trigger_b=trigger_b,
        trigger_c=trigger_c,
        trigger_d=trigger_d,
    )
    if severidad <= 0:
        return {"created": False, "reason": "no_severity", "riesgo": round(riesgo, 3)}

    last = (
        AlertaAcademica.objects.filter(alumno=nota.alumno, materia=nota.materia)
        .order_by("-creada_en", "-id")
        .first()
    )
    if last is not None:
        dias = (hoy - (getattr(last, "fecha_evento", hoy) or hoy)).days
        if dias < cooldown_dias:
            return {"created": False, "reason": "cooldown", "riesgo": round(riesgo, 3), "severidad": severidad}
        if dias < escalado_dias:
            return {"created": False, "reason": "cooldown_escalado", "riesgo": round(riesgo, 3), "severidad": severidad}

    trigger_map = {
        "materia": nota.materia,
        "A_TED_critico": trigger_a,
        "B_racha_2": trigger_b,
        "C_riesgo_sostenido": trigger_c,
        "D_caida_brusca": trigger_d,
    }

    alerta = AlertaAcademica.objects.create(
        alumno=nota.alumno,
        materia=nota.materia,
        cuatrimestre=getattr(nota, "cuatrimestre", None),
        severidad=severidad,
        riesgo_ponderado=Decimal(str(round(riesgo, 3))),
        triggers=trigger_map,
        ventana_desde=desde,
        ventana_hasta=hoy,
        fecha_evento=hoy,
        estado="activa",
        nota_disparadora=nota,
        creada_por=actor,
    )

    destinatarios = _destinatarios_alerta(nota.alumno)
    notifs = _crear_notificaciones_alerta(
        alumno=nota.alumno,
        destinatarios=destinatarios,
        severidad=severidad,
        riesgo=riesgo,
        trigger_map=trigger_map,
        alerta_id=alerta.id,
    )
    emails = _enviar_email_alerta(
        alumno=nota.alumno,
        destinatarios=destinatarios,
        severidad=severidad,
        riesgo=riesgo,
        trigger_map=trigger_map,
    )

    return {
        "created": True,
        "alerta_id": alerta.id,
        "severidad": severidad,
        "riesgo": round(riesgo, 3),
        "notificaciones": notifs,
        "emails": emails,
        "triggers": trigger_map,
    }
