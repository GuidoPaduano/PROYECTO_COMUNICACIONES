from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any
from collections import defaultdict

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from ..course_access import build_course_membership_q_for_refs, build_course_ref, filter_assignments_for_course
from ..models import AlertaAcademica, Nota, Notificacion
from ..resend_email import send_resend_email

try:
    from ..models_preceptores import PreceptorCurso  # type: ignore
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


def _alertas_qs_para_nota(nota: Nota):
    return AlertaAcademica.objects.filter(
        alumno=nota.alumno,
        materia=nota.materia,
    )


def _build_notas_ventana(*, alumno, materia: str, cuatrimestre, hoy):
    ventana_dias = _cfg_int("ALERTAS_ACADEMICAS_VENTANA_DIAS", 45)
    desde = hoy - timedelta(days=ventana_dias)
    qs = Nota.objects.filter(
        alumno=alumno,
        materia=materia,
        fecha__gte=desde,
        fecha__lte=hoy,
    )
    if cuatrimestre in (1, 2):
        qs = qs.filter(cuatrimestre=cuatrimestre)
    return list(qs.order_by("-fecha", "-id")), desde


def _estado_actual_alerta(*, alumno, materia: str, cuatrimestre, hoy):
    notas_ventana, desde = _build_notas_ventana(
        alumno=alumno,
        materia=materia,
        cuatrimestre=cuatrimestre,
        hoy=hoy,
    )
    return _estado_actual_alerta_from_notas(
        notas_ventana=notas_ventana,
        desde=desde,
        hoy=hoy,
    )


def _estado_actual_alerta_from_notas(*, notas_ventana: list[Nota], desde, hoy):
    nota_actual = notas_ventana[0] if notas_ventana else None
    riesgo, n_validas = _riesgo_ponderado(notas_ventana, hoy)
    trigger_a = nota_es_ted(nota_actual) if nota_actual is not None else False
    trigger_b = _trigger_racha(nota_actual, notas_ventana) if nota_actual is not None else False
    trigger_c = riesgo >= 0.65 and n_validas >= 3
    trigger_d = _trigger_caida_brusca(notas_ventana)
    return {
        "desde": desde,
        "riesgo": round(riesgo, 3),
        "n_validas": n_validas,
        "trigger_a": trigger_a,
        "trigger_b": trigger_b,
        "trigger_c": trigger_c,
        "trigger_d": trigger_d,
        "active": bool(trigger_a or trigger_b or trigger_c or trigger_d),
        "nota_actual": nota_actual,
    }


def _build_notas_ventana_lookup(*, keys, hoy):
    ventana_dias = _cfg_int("ALERTAS_ACADEMICAS_VENTANA_DIAS", 45)
    desde = hoy - timedelta(days=ventana_dias)
    alumno_ids = sorted({int(key[0]) for key in keys if key[0] is not None})
    materias = sorted({str(key[1] or "") for key in keys})

    if not alumno_ids or not materias:
        return {}, desde

    notas_qs = (
        Nota.objects.filter(
            alumno_id__in=alumno_ids,
            materia__in=materias,
            fecha__gte=desde,
            fecha__lte=hoy,
        )
        .order_by("alumno_id", "materia", "-fecha", "-id")
    )

    notas_por_par = defaultdict(list)
    notas_por_triple = defaultdict(list)
    for nota in notas_qs:
        pair_key = (int(getattr(nota, "alumno_id", 0) or 0), str(getattr(nota, "materia", "") or ""))
        notas_por_par[pair_key].append(nota)
        triple_key = pair_key + (getattr(nota, "cuatrimestre", None),)
        notas_por_triple[triple_key].append(nota)

    lookup = {}
    for alumno_id, materia, cuatrimestre in keys:
        pair_key = (int(alumno_id), str(materia or ""))
        if cuatrimestre in (1, 2):
            lookup[(int(alumno_id), str(materia or ""), cuatrimestre)] = list(
                notas_por_triple.get(pair_key + (cuatrimestre,), [])
            )
        else:
            lookup[(int(alumno_id), str(materia or ""), cuatrimestre)] = list(
                notas_por_par.get(pair_key, [])
            )
    return lookup, desde


def reconciliar_alertas_academicas(*, cursos=None, course_refs=None, school=None):
    hoy = timezone.localdate()
    base_qs = AlertaAcademica.objects.filter(estado="activa")
    if course_refs is None and cursos is not None:
        course_refs = [
            build_course_ref(school=school, course_code=curso)
            for curso in (cursos or [])
            if str(curso or "").strip()
        ]

    if course_refs is not None:
        course_q = build_course_membership_q_for_refs(
            course_refs,
            school_course_field="alumno__school_course",
            code_field="alumno__curso",
            school_field="alumno__school",
        )
        if course_q is None:
            return {"revisadas": 0, "cerradas": 0}
        base_qs = base_qs.filter(course_q)

    cerradas = 0
    revisadas = set()
    review_keys = []
    for alumno_id, materia, cuatrimestre in base_qs.order_by("-creada_en", "-id").values_list(
        "alumno_id",
        "materia",
        "cuatrimestre",
    ):
        if alumno_id is None:
            continue
        key = (int(alumno_id), str(materia or ""), cuatrimestre)
        if key in revisadas:
            continue
        revisadas.add(key)
        review_keys.append(key)

    notas_lookup, desde = _build_notas_ventana_lookup(keys=review_keys, hoy=hoy)
    for alumno_id, materia, cuatrimestre in review_keys:
        estado = _estado_actual_alerta_from_notas(
            notas_ventana=notas_lookup.get((alumno_id, materia, cuatrimestre), []),
            desde=desde,
            hoy=hoy,
        )
        if estado["active"]:
            continue

        cerradas += AlertaAcademica.objects.filter(
            alumno_id=alumno_id,
            materia=materia,
            cuatrimestre=cuatrimestre,
            estado="activa",
        ).update(estado="cerrada")

    return {"revisadas": len(review_keys), "cerradas": int(cerradas)}


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
            qs = filter_assignments_for_course(
                PreceptorCurso.objects.select_related("preceptor"),
                obj=alumno,
            )
            for pc in qs:
                _add(getattr(pc, "preceptor", None))
        except Exception:
            pass

    return destinatarios


def _course_display(alumno) -> str:
    school_course = getattr(alumno, "school_course", None)
    return (
        getattr(school_course, "name", None)
        or getattr(school_course, "code", None)
        or getattr(alumno, "curso", "")
        or "curso sin definir"
    )


def _course_meta(alumno) -> dict[str, Any]:
    return {
        "school_course_id": getattr(alumno, "school_course_id", None),
        "school_course_name": _course_display(alumno),
    }


def _crear_notificaciones_alerta(*, alumno, destinatarios, severidad: int, riesgo: float, trigger_map: dict[str, bool], alerta_id: int):
    if not destinatarios:
        return 0

    alumno_nombre = f"{(getattr(alumno, 'nombre', '') or '').strip()} {(getattr(alumno, 'apellido', '') or '').strip()}".strip()
    if not alumno_nombre:
        alumno_nombre = str(getattr(alumno, "id_alumno", "") or "Alumno")

    _TRIGGER_LABELS = {
        "A_TED_critico": "nota reprobada",
        "B_racha_2": "2 notas bajas seguidas",
        "C_riesgo_sostenido": "rendimiento bajo sostenido",
        "D_caida_brusca": "caída brusca de notas",
    }
    motivos = [
        _TRIGGER_LABELS.get(k, k)
        for k, v in trigger_map.items()
        if k.startswith(("A_", "B_", "C_", "D_")) and v
    ]
    motivos_txt = ", ".join(motivos) if motivos else "bajo rendimiento"
    materia_txt = trigger_map.get("materia", "") or "N/A"
    course_name = _course_display(alumno)
    titulo = f"{alumno_nombre} necesita atención académica"
    descripcion = f"{materia_txt} en {course_name} · {motivos_txt}"

    notifs = []
    school_ref = getattr(alumno, "school", None)
    for dest in destinatarios:
        notifs.append(
            Notificacion(
                school=school_ref,
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
                    **_course_meta(alumno),
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

    _TRIGGER_LABELS = {
        "A_TED_critico": "nota reprobada",
        "B_racha_2": "2 notas bajas seguidas",
        "C_riesgo_sostenido": "rendimiento bajo sostenido",
        "D_caida_brusca": "caída brusca de notas",
    }
    motivos = [
        _TRIGGER_LABELS.get(k, k)
        for k, v in trigger_map.items()
        if k.startswith(("A_", "B_", "C_", "D_")) and v
    ]
    motivos_txt = ", ".join(motivos) if motivos else "bajo rendimiento"
    course_name = _course_display(alumno)
    subject = f"[Alerta académica] {alumno_nombre}"
    text = (
        f"Alumno: {alumno_nombre}\n"
        f"Curso: {course_name}\n"
        f"Materia: {trigger_map.get('materia', '')}\n"
        f"Motivo: {motivos_txt}\n"
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


def evaluar_alerta_nota(*, nota: Nota, actor=None, send_email: bool = True) -> dict[str, Any]:
    hoy = timezone.localdate()
    cooldown_dias = _cfg_int("ALERTAS_ACADEMICAS_COOLDOWN_DIAS", 7)
    escalado_dias = _cfg_int("ALERTAS_ACADEMICAS_ESCALADO_DIAS", 14)
    notas_ventana, desde = _build_notas_ventana(
        alumno=nota.alumno,
        materia=nota.materia,
        cuatrimestre=getattr(nota, "cuatrimestre", None),
        hoy=hoy,
    )
    current = _estado_actual_alerta_from_notas(
        notas_ventana=notas_ventana,
        desde=desde,
        hoy=hoy,
    )

    riesgo = current["riesgo"]
    n_validas = current["n_validas"]
    trigger_a = current["trigger_a"]
    trigger_b = current["trigger_b"]
    trigger_c = current["trigger_c"]
    trigger_d = current["trigger_d"]

    if not (trigger_a or trigger_b or trigger_c or trigger_d):
        cerradas = _alertas_qs_para_nota(nota).filter(estado="activa").update(estado="cerrada")
        return {
            "created": False,
            "reason": "no_trigger",
            "riesgo": round(riesgo, 3),
            "closed": int(cerradas or 0),
        }

    severidad = _severidad_binaria(
        trigger_a=trigger_a,
        trigger_b=trigger_b,
        trigger_c=trigger_c,
        trigger_d=trigger_d,
    )
    if severidad <= 0:
        return {"created": False, "reason": "no_severity", "riesgo": round(riesgo, 3)}

    last = _alertas_qs_para_nota(nota).order_by("-creada_en", "-id").first()
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
    emails = 0
    if send_email:
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


def evaluar_alertas_notas_bulk(*, notas, actor=None, send_email: bool = False) -> dict[str, Any]:
    hoy = timezone.localdate()
    cooldown_dias = _cfg_int("ALERTAS_ACADEMICAS_COOLDOWN_DIAS", 7)
    escalado_dias = _cfg_int("ALERTAS_ACADEMICAS_ESCALADO_DIAS", 14)

    latest_by_key = {}
    for nota in notas or []:
        alumno_id = getattr(nota, "alumno_id", None)
        materia = str(getattr(nota, "materia", "") or "")
        if alumno_id is None or not materia:
            continue
        key = (int(alumno_id), materia, getattr(nota, "cuatrimestre", None))
        prev = latest_by_key.get(key)
        if prev is None:
            latest_by_key[key] = nota
            continue

        prev_fecha = getattr(prev, "fecha", None)
        curr_fecha = getattr(nota, "fecha", None)
        prev_id = getattr(prev, "id", 0) or 0
        curr_id = getattr(nota, "id", 0) or 0
        if (curr_fecha, curr_id) >= (prev_fecha, prev_id):
            latest_by_key[key] = nota

    keys = list(latest_by_key.keys())
    if not keys:
        return {"created": 0, "evaluated": 0, "closed": 0}

    notas_lookup, desde = _build_notas_ventana_lookup(keys=keys, hoy=hoy)
    alumno_ids = sorted({alumno_id for alumno_id, _, _ in keys})
    materias = sorted({materia for _, materia, _ in keys})

    last_by_pair = {}
    for alerta in AlertaAcademica.objects.filter(
        alumno_id__in=alumno_ids,
        materia__in=materias,
    ).order_by("alumno_id", "materia", "-creada_en", "-id"):
        pair_key = (int(getattr(alerta, "alumno_id", 0) or 0), str(getattr(alerta, "materia", "") or ""))
        if pair_key not in last_by_pair:
            last_by_pair[pair_key] = alerta

    created = 0
    closed = 0
    no_trigger_q = Q()

    for key in keys:
        nota = latest_by_key[key]
        alumno_id, materia, cuatrimestre = key
        current = _estado_actual_alerta_from_notas(
            notas_ventana=notas_lookup.get(key, []),
            desde=desde,
            hoy=hoy,
        )

        riesgo = current["riesgo"]
        trigger_a = current["trigger_a"]
        trigger_b = current["trigger_b"]
        trigger_c = current["trigger_c"]
        trigger_d = current["trigger_d"]

        if not (trigger_a or trigger_b or trigger_c or trigger_d):
            no_trigger_q |= Q(alumno_id=alumno_id, materia=materia, estado="activa")
            continue

        severidad = _severidad_binaria(
            trigger_a=trigger_a,
            trigger_b=trigger_b,
            trigger_c=trigger_c,
            trigger_d=trigger_d,
        )
        if severidad <= 0:
            continue

        last = last_by_pair.get((alumno_id, materia))
        if last is not None:
            dias = (hoy - (getattr(last, "fecha_evento", hoy) or hoy)).days
            if dias < cooldown_dias or dias < escalado_dias:
                continue

        trigger_map = {
            "materia": materia,
            "A_TED_critico": trigger_a,
            "B_racha_2": trigger_b,
            "C_riesgo_sostenido": trigger_c,
            "D_caida_brusca": trigger_d,
        }
        create_kwargs = {
            "alumno": nota.alumno,
            "materia": materia,
            "cuatrimestre": cuatrimestre,
            "severidad": severidad,
            "riesgo_ponderado": Decimal(str(round(riesgo, 3))),
            "triggers": trigger_map,
            "ventana_desde": desde,
            "ventana_hasta": hoy,
            "fecha_evento": hoy,
            "estado": "activa",
            "nota_disparadora": nota,
            "creada_por": actor,
        }
        school_ref = getattr(nota, "school", None) or getattr(getattr(nota, "alumno", None), "school", None)
        if school_ref is not None:
            create_kwargs["school"] = school_ref

        alerta = AlertaAcademica.objects.create(**create_kwargs)
        destinatarios = _destinatarios_alerta(nota.alumno)
        _crear_notificaciones_alerta(
            alumno=nota.alumno,
            destinatarios=destinatarios,
            severidad=severidad,
            riesgo=riesgo,
            trigger_map=trigger_map,
            alerta_id=alerta.id,
        )
        if send_email:
            _enviar_email_alerta(
                alumno=nota.alumno,
                destinatarios=destinatarios,
                severidad=severidad,
                riesgo=riesgo,
                trigger_map=trigger_map,
            )
        created += 1

    if no_trigger_q:
        closed = AlertaAcademica.objects.filter(no_trigger_q).update(estado="cerrada")

    return {"created": created, "evaluated": len(keys), "closed": int(closed or 0)}
