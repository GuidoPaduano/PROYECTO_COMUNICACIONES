# calificaciones/api_asistencias/_views.py
"""
Vistas públicas de la API de asistencias.
"""
from __future__ import annotations

from datetime import date as date_cls
from typing import Any, Dict, List

from django.conf import settings
from django.db.models import Q
from django.utils.dateparse import parse_date

from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    parser_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser

from ..jwt_auth import CookieJWTAuthentication as JWTAuthentication
from ..tasks import evaluar_alertas_inasistencia_task, evaluar_alerta_inasistencia_task
from ..models import Alumno, Asistencia
from ..models import resolve_school_course_for_value
from ..schools import get_request_school, scope_queryset_to_school
from ..signatures import claim_signature
from ..utils_cursos import resolve_course_reference

from ._acceso import _can_justify, _can_sign_asistencia, _can_edit_asistencia_detalle
from ._helpers import (
    _alumno_base_qs,
    _alumnos_por_curso_qs,
    _asistencia_base_qs,
    _asistencias_alumno_response,
    _bulk_upsert_asistencias,
    _can_manage_course_attendance,
    _can_view_alumno_asistencia,
    _coerce_json,
    _curso_label,
    _cursos_de_usuario,
    _err,
    _extract_items,
    _first_scalar,
    _infer_estado,
    _norm_bool,
    _norm_estado,
    _notify_inasistencias_bulk,
    _ok_response,
    _public_course_payload,
    _serialize_alumno_brief,
    _serialize_asistencia_item,
    _tipo_choices,
    _try_parse_json,
)

LEGACY_COURSE_DEPRECATED_DETAIL = "El parámetro 'curso' está deprecado en este endpoint. Usa school_course_id."


# =========================================================
#  Preceptor: cursos
# =========================================================
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def preceptor_cursos(request):
    active_school = get_request_school(request)
    cursos = _cursos_de_usuario(request.user, school=active_school)
    data = []
    for c in cursos:
        school_course = resolve_school_course_for_value(school=active_school, curso=c) if active_school is not None else None
        data.append(
            {
                "curso": c,
                "code": c,
                "nombre": _curso_label(c, school=active_school),
                "school_course_id": getattr(school_course, "id", None),
            }
        )
    return _ok_response({"cursos": data})


# =========================================================
#  Tipos de asistencia (combo del front)
# =========================================================
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def tipos_asistencia(request):
    data = []
    for v, lbl in _tipo_choices():
        data.append({"id": v, "nombre": lbl, "value": v, "label": lbl})
    return Response(data)


# =========================================================
#  Registrar asistencias
# =========================================================
@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def registrar_asistencias(request):
    active_school = get_request_school(request)
    payload = _coerce_json(request)

    # por defecto NO devolvemos items (para que sea rápido y no pese)
    return_items = _norm_bool(payload.get("return_items"))
    if return_items is None:
        return_items = False

    # -----------------------------------------------------
    # Formato C: mapping id->estado
    #   {school_course_id, fecha, tipo_asistencia|tipo, asistencias:{ "418": true, ... }}
    # -----------------------------------------------------
    if isinstance(payload, dict) and ("asistencias" in payload or "asistenciasPayload" in payload):
        raw_map = payload.get("asistencias", payload.get("asistenciasPayload"))
        raw_map = _try_parse_json(raw_map)

        if isinstance(raw_map, dict):
            school_course_ref, curso, course_error = resolve_course_reference(
                school=active_school,
                raw_course=_first_scalar(payload.get("curso") or ""),
                raw_school_course_id=_first_scalar(payload.get("school_course_id") or ""),
                required=True,
            )
            tipo_asistencia = str(
                _first_scalar(payload.get("tipo_asistencia") or payload.get("tipo") or payload.get("materia") or "") or ""
            ).strip()

            fecha_raw = _first_scalar(payload.get("fecha") or payload.get("date"))
            fecha = parse_date(str(fecha_raw)) if fecha_raw else date_cls.today()

            if course_error:
                return _err(course_error, 400)
            if not tipo_asistencia:
                return _err("Falta tipo_asistencia/tipo", 400)
            if active_school is not None and school_course_ref is None:
                return _err("No existe ese curso en el colegio activo.", 400)

            if not _can_manage_course_attendance(request.user, curso, school=active_school, school_course=school_course_ref):
                return _err("No tenés permisos para ese curso.", 403)

            # resolvemos alumnos en BULK (evita N queries)
            keys = [str(k).strip() for k in raw_map.keys()]
            id_ints: List[int] = []
            legajos: List[str] = []
            for k in keys:
                if k.isdigit():
                    try:
                        id_ints.append(int(k))
                    except Exception:
                        pass
                else:
                    legajos.append(k)

            alumnos_qs = _alumnos_por_curso_qs(curso, school=active_school).filter(
                Q(pk__in=id_ints) | Q(id_alumno__in=legajos)
            )

            alumnos_list = list(alumnos_qs)
            by_pk = {str(a.id): a for a in alumnos_list}
            by_legajo = {str(getattr(a, "id_alumno", "")).strip(): a for a in alumnos_list}

            estado_by_id: Dict[int, Dict[str, bool]] = {}
            errores = 0

            for k, v in raw_map.items():
                key = str(k).strip()
                st = _norm_estado(v)
                if st is None:
                    b = _norm_bool(v)
                    if b is None:
                        b = bool(v)
                    st = {"presente": bool(b), "tarde": False}

                alumno = by_pk.get(key) if key.isdigit() else by_legajo.get(key)
                if not alumno:
                    errores += 1
                    continue

                if not bool(st.get("presente", True)):
                    st["tarde"] = False

                estado_by_id[int(alumno.id)] = {"presente": bool(st.get("presente", True)), "tarde": bool(st.get("tarde", False))}

            alumno_ids = sorted(list(estado_by_id.keys()))
            if not alumno_ids and errores > 0:
                return _err(
                    "No se pudo guardar ninguna asistencia. Revisá que las claves de 'asistencias' sean IDs (PK) o legajos válidos del curso.",
                    400,
                    {"guardadas": 0, "errores": errores},
                )

            # upsert masivo
            try:
                res = _bulk_upsert_asistencias(
                    alumno_ids,
                    fecha,
                    tipo_asistencia,
                    estado_by_id,
                    school=active_school,
                )
            except Exception:
                return _err("Error guardando asistencias (bulk).", 500)

            try:
                _notify_inasistencias_bulk(
                    alumno_ids=sorted(set(res.get("ausentes") or [])),
                    fecha=fecha,
                    tipo_asistencia=tipo_asistencia,
                    actor=getattr(request, "user", None),
                    school=active_school,
                )
            except Exception:
                pass
            try:
                evaluar_alertas_inasistencia_task.delay(
                    alumno_ids=sorted(set(res.get("afectados") or [])),
                    tipo_asistencia=tipo_asistencia,
                    actor_id=getattr(getattr(request, "user", None), "pk", None),
                )
            except Exception:
                pass

            items_out: List[Dict[str, Any]] = []
            if return_items and alumno_ids:
                qs = scope_queryset_to_school(
                    Asistencia.objects.filter(
                        alumno_id__in=alumno_ids,
                        fecha=fecha,
                        tipo_asistencia=tipo_asistencia,
                    ),
                    active_school,
                ).select_related("alumno", "alumno__school_course")
                for obj in qs:
                    items_out.append(_serialize_asistencia_item(obj, curso=curso, school=active_school))

            response_payload = {
                "fecha": str(fecha),
                "tipo_asistencia": tipo_asistencia,
                "guardadas": res.get("guardadas", 0),
                "errores": int(errores) + int(res.get("errores", 0)),
                "items": items_out if return_items else [],
            }
            response_payload.update(
                _public_course_payload(school_course=school_course_ref, curso=curso, school=active_school)
            )
            return _ok_response(response_payload)

    # -----------------------------------------------------
    # Formato A: presentes/tardes por curso (lista de IDs)
    #   {school_course_id, fecha, tipo_asistencia|tipo, presentes:[ids]}
    # -----------------------------------------------------
    if isinstance(payload, dict) and (
        "presentes" in payload or "presentes_ids" in payload or "presentesId" in payload
    ):
        school_course_ref, curso, course_error = resolve_course_reference(
            school=active_school,
            raw_course=_first_scalar(payload.get("curso") or ""),
            raw_school_course_id=_first_scalar(payload.get("school_course_id") or ""),
            required=True,
        )
        tipo_asistencia = str(
            _first_scalar(payload.get("tipo_asistencia") or payload.get("tipo") or payload.get("materia") or "") or ""
        ).strip()

        fecha_raw = _first_scalar(payload.get("fecha") or payload.get("date"))
        fecha = parse_date(str(fecha_raw)) if fecha_raw else date_cls.today()

        presentes = payload.get("presentes") or payload.get("presentes_ids") or payload.get("presentesId") or []
        tardes = payload.get("tardes") or payload.get("tardes_ids") or payload.get("tardesId") or []
        presentes = _try_parse_json(presentes)
        if not isinstance(presentes, list):
            presentes = []
        tardes = _try_parse_json(tardes)
        if not isinstance(tardes, list):
            tardes = []

        if course_error:
            return _err(course_error, 400)
        if not tipo_asistencia:
            return _err("Falta tipo_asistencia/tipo", 400)
        if active_school is not None and school_course_ref is None:
            return _err("No existe ese curso en el colegio activo.", 400)

        if not _can_manage_course_attendance(request.user, curso, school=active_school, school_course=school_course_ref):
            return _err("No tenés permisos para ese curso.", 403)

        alumno_ids = list(_alumnos_por_curso_qs(curso, school=active_school).values_list("id", flat=True))
        if not alumno_ids:
            response_payload = {
                "fecha": str(fecha),
                "tipo_asistencia": tipo_asistencia,
                "guardadas": 0,
                "errores": 0,
                "items": [],
            }
            response_payload.update(
                _public_course_payload(school_course=school_course_ref, curso=curso, school=active_school)
            )
            return _ok_response(response_payload)

        presentes_set = set()
        for x in presentes:
            try:
                presentes_set.add(int(x))
            except Exception:
                pass
        tardes_set = set()
        for x in tardes:
            try:
                tardes_set.add(int(x))
            except Exception:
                pass

        presente_by_id = {aid: (aid in presentes_set) for aid in alumno_ids}
        # FIX: el bulk upsert espera {alumno_id: {presente, tarde}}
        estado_by_id = {
            aid: {
                "presente": bool(presente_by_id[aid]) or (aid in tardes_set),
                "tarde": (aid in tardes_set),
            }
            for aid in alumno_ids
        }

        try:
            res = _bulk_upsert_asistencias(
                alumno_ids,
                fecha,
                tipo_asistencia,
                estado_by_id,
                school=active_school,
            )
        except Exception:
            return _err("Error guardando asistencias (bulk).", 500)

        try:
            _notify_inasistencias_bulk(
                alumno_ids=sorted(set(res.get("ausentes") or [])),
                fecha=fecha,
                tipo_asistencia=tipo_asistencia,
                actor=getattr(request, "user", None),
                school=active_school,
            )
        except Exception:
            pass
        try:
            evaluar_alertas_inasistencia_task.delay(
                alumno_ids=sorted(set(res.get("afectados") or [])),
                tipo_asistencia=tipo_asistencia,
                actor_id=getattr(getattr(request, "user", None), "pk", None),
            )
        except Exception:
            pass

        items_out: List[Dict[str, Any]] = []
        if return_items:
            qs = scope_queryset_to_school(
                Asistencia.objects.filter(
                    alumno_id__in=alumno_ids,
                    fecha=fecha,
                    tipo_asistencia=tipo_asistencia,
                ),
                active_school,
            ).select_related("alumno", "alumno__school_course")
            for obj in qs:
                items_out.append(_serialize_asistencia_item(obj, curso=curso, school=active_school))

        response_payload = {
            "fecha": str(fecha),
            "tipo_asistencia": tipo_asistencia,
            "guardadas": res.get("guardadas", 0),
            "errores": res.get("errores", 0),
            "items": items_out if return_items else [],
        }
        response_payload.update(
            _public_course_payload(school_course=school_course_ref, curso=curso, school=active_school)
        )
        return _ok_response(response_payload)

    # -----------------------------------------------------
    # Formato B: items
    # -----------------------------------------------------
    items = _extract_items(payload)
    if not items:
        return _err("Falta 'asistencias', 'presentes' o 'items'.", 400)

    fecha_global = None
    tipo_global = None
    curso_global = None
    if isinstance(payload, dict):
        fg = _first_scalar(payload.get("fecha") or payload.get("date"))
        fecha_global = parse_date(str(fg)) if fg else None
        tipo_global = str(_first_scalar(payload.get("tipo_asistencia") or payload.get("tipo") or payload.get("materia") or "") or "").strip() or None
        global_school_course_ref, curso_global, global_course_error = resolve_course_reference(
            school=active_school,
            raw_course=_first_scalar(payload.get("curso") or ""),
            raw_school_course_id=_first_scalar(payload.get("school_course_id") or ""),
            required=False,
        )
        if global_course_error:
            return _err(global_course_error, 400)
        if active_school is not None and curso_global and global_school_course_ref is None:
            return _err("No existe ese curso en el colegio activo.", 400)

    guardadas = 0
    errores = 0
    items_out: List[Dict[str, Any]] = []
    afectados_ids_por_tipo: Dict[str, set] = {}

    # Pre-fetch all alumnos needed in this batch to avoid N+1 queries
    _batch_pks: set = set()
    _batch_legajos: set = set()
    for _it in items:
        _it_parsed = _try_parse_json(_it)
        if isinstance(_it_parsed, dict):
            _aid = _it_parsed.get("alumno_id") or _it_parsed.get("alumno")
            _leg = _it_parsed.get("id_alumno") or _it_parsed.get("legajo")
            if _aid:
                try:
                    _batch_pks.add(int(_aid))
                except (ValueError, TypeError):
                    pass
            if _leg:
                _batch_legajos.add(str(_leg))

    _alumno_by_pk: Dict[int, Any] = {}
    _alumno_by_legajo: Dict[str, Any] = {}
    _base_alumno_qs = scope_queryset_to_school(Alumno.objects.all(), active_school).select_related("school_course", "school")
    if _batch_pks:
        for _a in _base_alumno_qs.filter(pk__in=_batch_pks):
            _alumno_by_pk[_a.pk] = _a
    if _batch_legajos:
        for _a in _base_alumno_qs.filter(id_alumno__in=_batch_legajos):
            _alumno_by_legajo[_a.id_alumno] = _a

    for it in items:
        it = _try_parse_json(it)
        if not isinstance(it, dict):
            errores += 1
            continue

        alumno = None
        alumno_id = it.get("alumno_id") or it.get("alumno")
        legajo = it.get("id_alumno") or it.get("legajo")

        try:
            if alumno_id:
                alumno = _alumno_by_pk.get(int(alumno_id))
            elif legajo:
                alumno = _alumno_by_legajo.get(str(legajo))
            if alumno is None:
                errores += 1
                continue
        except Exception:
            errores += 1
            continue

        item_raw_course = _first_scalar(it.get("curso") or "")
        item_raw_school_course_id = _first_scalar(it.get("school_course_id") or payload.get("school_course_id") or "")

        item_school_course_ref = global_school_course_ref
        curso_item = curso_global or ""
        item_course_error = None

        if item_raw_course or item_raw_school_course_id:
            item_school_course_ref, curso_item, item_course_error = resolve_course_reference(
                school=active_school,
                raw_course=item_raw_course,
                raw_school_course_id=item_raw_school_course_id,
                required=False,
            )

        if item_course_error == LEGACY_COURSE_DEPRECATED_DETAIL:
            return _err(item_course_error, 400)
        if item_course_error:
            errores += 1
            continue
        if item_school_course_ref is None and not curso_item:
            item_school_course_ref = getattr(alumno, "school_course", None)
            curso_item = (alumno.curso or "").strip()
        if not _can_manage_course_attendance(
            request.user,
            curso_item,
            school=active_school,
            school_course=item_school_course_ref or getattr(alumno, "school_course", None),
        ):
            errores += 1
            continue

        fr = it.get("fecha") or it.get("date")
        fecha = parse_date(str(fr)) if fr else (fecha_global or date_cls.today())

        tipo_asistencia = (it.get("tipo_asistencia") or it.get("tipo") or it.get("materia") or tipo_global or "").strip()
        if not tipo_asistencia:
            tipo_asistencia = "clases"

        st = _infer_estado(it)
        if st is None:
            errores += 1
            continue
        presente = bool(st.get('presente', True))
        tarde = bool(st.get('tarde', False))
        if not presente:
            tarde = False
        if presente is None:
            presente = bool(it.get("presente", True))

        try:
            prev = scope_queryset_to_school(Asistencia.objects.filter(
                alumno=alumno, fecha=fecha, tipo_asistencia=tipo_asistencia
            ), active_school).first()
            obj, _created = scope_queryset_to_school(Asistencia.objects.all(), active_school).update_or_create(
                alumno=alumno,
                fecha=fecha,
                tipo_asistencia=tipo_asistencia,
                defaults={"school": getattr(alumno, "school", None) or active_school, "presente": bool(presente), "tarde": bool(tarde)},
            )
            key_tipo = str(tipo_asistencia or "clases")
            if key_tipo not in afectados_ids_por_tipo:
                afectados_ids_por_tipo[key_tipo] = set()
            afectados_ids_por_tipo[key_tipo].add(int(alumno.id))
            guardadas += 1
            if (prev is None and (not bool(presente))) or (prev is not None and bool(prev.presente) and (not bool(presente))):
                try:
                    _notify_inasistencias_bulk(
                        alumno_ids=[alumno.id],
                        fecha=fecha,
                        tipo_asistencia=tipo_asistencia,
                        actor=getattr(request, "user", None),
                        school=active_school,
                    )
                except Exception:
                    pass
            if return_items:
                items_out.append(_serialize_asistencia_item(obj, alumno=alumno, school=active_school))
        except Exception:
            errores += 1

    try:
        actor_id = getattr(getattr(request, "user", None), "pk", None)
        for tipo_eval, ids_eval in afectados_ids_por_tipo.items():
            evaluar_alertas_inasistencia_task.delay(
                alumno_ids=sorted(ids_eval),
                tipo_asistencia=tipo_eval,
                actor_id=actor_id,
            )
    except Exception:
        pass

    return _ok_response({
        "guardadas": guardadas,
        "errores": errores,
        "items": items_out if return_items else [],
    })


# =========================================================
#  Justificar inasistencia / tardanza
# =========================================================
@api_view(["GET", "PATCH", "POST", "PUT"])  # GET para debug/compat + PATCH preferido, POST/PUT compat
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def justificar_asistencia(request, pk: int):
    """
    Marca una asistencia como justificada o no justificada.

    Body JSON:
      { "justificada": true/false }
    """
    # Permiso: SOLO Preceptor (o admin) puede justificar.
    if not _can_justify(getattr(request, "user", None)):
        return _err("No tenés permisos para justificar asistencias.", status=403)

    # GET: devolvemos estado actual (útil para debug y para clientes que quieran refrescar)
    active_school = get_request_school(request)

    if request.method == "GET":
        try:
            obj = _asistencia_base_qs(active_school).get(pk=pk)
        except Asistencia.DoesNotExist:
            return _err("Asistencia no encontrada.", status=404)

        # Permisos por curso
        curso = getattr(obj.alumno, "curso", None)
        if not _can_manage_course_attendance(
            request.user,
            curso,
            school=active_school,
            school_course=getattr(obj.alumno, "school_course", None),
        ):
            return _err("No tenés permisos para ese curso.", status=403)

        falta_valor = 0.0 if bool(getattr(obj, "justificada", False)) else (
            1.0 if (not bool(obj.presente)) else (0.5 if bool(getattr(obj, "tarde", False)) else 0.0)
        )

        return _ok_response({
            "id": obj.id,
            "alumno_id": obj.alumno_id,
            "fecha": str(obj.fecha),
            "tipo_asistencia": obj.tipo_asistencia,
            "presente": bool(obj.presente),
            "tarde": bool(getattr(obj, "tarde", False)),
            "justificada": bool(getattr(obj, "justificada", False)),
            "firmada": bool(getattr(obj, "firmada", False)),
            "firmada_en": obj.firmada_en.isoformat() if getattr(obj, "firmada_en", None) else None,
            "falta_valor": falta_valor,
        })

    # Parseo JSON flexible
    data = _coerce_json(request)
    if not isinstance(data, dict):
        data = {}

    val = data.get("justificada", None)
    b = _norm_bool(val)
    if b is None:
        # toggle si no mandan valor
        b = None

    try:
        obj = _asistencia_base_qs(active_school).get(pk=pk)
    except Asistencia.DoesNotExist:
        return _err("Asistencia no encontrada.", status=404)

    # Permisos por curso
    curso = getattr(obj.alumno, "curso", None)
    if not _can_manage_course_attendance(
        request.user,
        curso,
        school=active_school,
        school_course=getattr(obj.alumno, "school_course", None),
    ):
        return _err("No tenés permisos para ese curso.", status=403)

    # Solo tiene sentido justificar si es Ausente o Tarde
    es_presente = bool(obj.presente) and (not bool(getattr(obj, "tarde", False)))
    if es_presente:
        return _err("No se puede justificar un presente.", status=400)

    nueva = (not bool(getattr(obj, "justificada", False))) if b is None else bool(b)

    setattr(obj, "justificada", nueva)
    obj.save(update_fields=["justificada"])
    try:
        evaluar_alerta_inasistencia_task.delay(
            alumno_id=obj.alumno_id,
            asistencia_id=obj.pk,
            tipo_asistencia=getattr(obj, "tipo_asistencia", "clases"),
            actor_id=getattr(getattr(request, "user", None), "pk", None),
        )
    except Exception:
        pass

    falta_valor = 0.0 if nueva else (1.0 if (not bool(obj.presente)) else (0.5 if bool(getattr(obj, "tarde", False)) else 0.0))

    return _ok_response({
        "id": obj.id,
        "alumno_id": obj.alumno_id,
        "fecha": str(obj.fecha),
        "tipo_asistencia": obj.tipo_asistencia,
        "presente": bool(obj.presente),
        "tarde": bool(getattr(obj, "tarde", False)),
        "justificada": bool(getattr(obj, "justificada", False)),
        "firmada": bool(getattr(obj, "firmada", False)),
        "firmada_en": obj.firmada_en.isoformat() if getattr(obj, "firmada_en", None) else None,
        "falta_valor": falta_valor,
    })


@api_view(["GET", "POST", "PATCH"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def firmar_asistencia(request, pk: int):
    active_school = get_request_school(request)
    try:
        obj = _asistencia_base_qs(active_school).get(pk=pk)
    except Asistencia.DoesNotExist:
        return _err("Asistencia no encontrada.", status=404)

    if not _can_sign_asistencia(getattr(request, "user", None), obj.alumno):
        return _err("No tenés permisos para firmar esta asistencia.", status=403)

    if request.method == "GET":
        return _ok_response({
            "id": obj.id,
            "alumno_id": obj.alumno_id,
            "fecha": str(obj.fecha),
            "tipo_asistencia": obj.tipo_asistencia,
            "firmada": bool(getattr(obj, "firmada", False)),
            "firmada_en": obj.firmada_en.isoformat() if getattr(obj, "firmada_en", None) else None,
        })

    es_presente = bool(obj.presente) and (not bool(getattr(obj, "tarde", False)))
    if es_presente:
        return _err("No se puede firmar un presente.", 400)

    if bool(getattr(obj, "firmada", False)):
        return _err(
            "La inasistencia ya fue firmada.",
            400,
            {
                "id": obj.id,
                "alumno_id": obj.alumno_id,
                "firmada": True,
                "firmada_en": obj.firmada_en.isoformat() if getattr(obj, "firmada_en", None) else None,
            },
        )

    if not claim_signature(obj, user=request.user):
        return _err(
            "La inasistencia ya fue firmada.",
            400,
            {
                "id": obj.id,
                "alumno_id": obj.alumno_id,
                "firmada": True,
                "firmada_en": obj.firmada_en.isoformat() if obj.firmada_en else None,
            },
        )

    return _ok_response({
        "id": obj.id,
        "alumno_id": obj.alumno_id,
        "fecha": str(obj.fecha),
        "tipo_asistencia": obj.tipo_asistencia,
        "firmada": True,
        "firmada_en": obj.firmada_en.isoformat() if obj.firmada_en else None,
    })


# =========================================================
#  Editar detalle (observación) de una asistencia
# =========================================================
@api_view(["GET", "PATCH", "POST", "PUT"])  # GET para leer; PATCH preferido; POST/PUT compat
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def editar_detalle_asistencia(request, pk: int):
    """
    Permite a un preceptor (o admin) cargar/editar el detalle (observación) de una asistencia.

    Body JSON (cualquiera de estas keys):
      { "detalle": "..." }  | { "observacion": "..." } | { "observaciones": "..." }

    Respuesta:
      { id, observacion, detalle, ... }
    """
    active_school = get_request_school(request)
    try:
        obj = _asistencia_base_qs(active_school).get(pk=pk)
    except Asistencia.DoesNotExist:
        return _err("Asistencia no encontrada.", status=404)

    if not _can_edit_asistencia_detalle(getattr(request, "user", None), obj.alumno):
        return _err("No tenés permisos para editar el detalle de asistencias.", status=403)

    # Permisos por curso (mismo criterio que justificar)
    curso = getattr(obj.alumno, "curso", None)
    if not _can_manage_course_attendance(
        request.user,
        curso,
        school=active_school,
        school_course=getattr(obj.alumno, "school_course", None),
    ):
        return _err("No tenés permisos para ese curso.", status=403)

    if request.method == "GET":
        return _ok_response({
            "id": obj.id,
            "alumno_id": obj.alumno_id,
            "fecha": str(obj.fecha),
            "tipo_asistencia": obj.tipo_asistencia,
            "presente": bool(obj.presente),
            "tarde": bool(getattr(obj, "tarde", False)),
            "justificada": bool(getattr(obj, "justificada", False)),
            "observacion": getattr(obj, "observacion", "") or "",
            "detalle": getattr(obj, "observacion", "") or "",
        })

    body = _coerce_json(request)
    raw = (
        body.get("detalle")
        if body.get("detalle") is not None
        else body.get("observacion")
        if body.get("observacion") is not None
        else body.get("observaciones")
        if body.get("observaciones") is not None
        else body.get("comentario")
    )

    if raw is None:
        return _err("Falta 'detalle' (o 'observacion').", status=400)

    detalle = str(raw).strip()

    # límite razonable por si el front manda cualquier cosa
    if len(detalle) > 255:
        detalle = detalle[:255]

    setattr(obj, "observacion", detalle)
    obj.save(update_fields=["observacion"])

    return _ok_response({
        "id": obj.id,
        "alumno_id": obj.alumno_id,
        "fecha": str(obj.fecha),
        "tipo_asistencia": obj.tipo_asistencia,
        "presente": bool(obj.presente),
        "tarde": bool(getattr(obj, "tarde", False)),
        "justificada": bool(getattr(obj, "justificada", False)),
        "observacion": getattr(obj, "observacion", "") or "",
        "detalle": getattr(obj, "observacion", "") or "",
    })


# =========================================================
#  Listados (GET)
# =========================================================
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def asistencias_por_alumno(request, alumno_id=None):
    """GET:
    - /api/asistencias/alumno/<int:alumno_id>/
    - /api/asistencias/?alumno=<id> / ?alumno_id=<id>
    - /api/asistencias/?id_alumno=<legajo>
    """
    active_school = get_request_school(request)
    aid = alumno_id or request.GET.get("alumno") or request.GET.get("alumno_id")
    codigo = request.GET.get("id_alumno") or request.GET.get("legajo")

    alumno = None
    if aid:
        try:
            alumno = _alumno_base_qs(active_school).get(pk=int(aid))
        except Exception:
            alumno = None
    if alumno is None and codigo:
        try:
            alumno = _alumno_base_qs(active_school).get(id_alumno=str(codigo))
        except Exception:
            alumno = None

    if alumno is None:
        return Response({"detail": "Alumno no encontrado"}, status=404)

    if not _can_view_alumno_asistencia(request.user, alumno):
        return Response({"detail": "No autorizado."}, status=403)

    return _asistencias_alumno_response(alumno, school=active_school, request=request)


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def asistencias_por_codigo(request, id_alumno):
    active_school = get_request_school(request)
    try:
        alumno = _alumno_base_qs(active_school).get(id_alumno=str(id_alumno))
    except Exception:
        return Response({"detail": "Alumno no encontrado"}, status=404)
    if not _can_view_alumno_asistencia(request.user, alumno):
        return Response({"detail": "No autorizado."}, status=403)
    return _asistencias_alumno_response(alumno, school=active_school, request=request)


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def asistencias_por_curso_y_fecha(request):
    """
    GET /api/asistencias/curso/?school_course_id=14&fecha=YYYY-MM-DD&tipo=informatica
    Requiere school_course_id para seleccionar curso.
    """
    active_school = get_request_school(request)
    school_course_ref, curso, course_error = resolve_course_reference(
        school=active_school,
        raw_course=request.GET.get("curso"),
        raw_school_course_id=request.GET.get("school_course_id"),
        required=True,
    )
    fecha = parse_date(str(request.GET.get("fecha") or "")) if request.GET.get("fecha") else None
    tipo = (request.GET.get("tipo") or request.GET.get("tipo_asistencia") or request.GET.get("materia") or "").strip()

    if course_error:
        return Response({"detail": course_error}, status=400)
    if active_school is not None and school_course_ref is None:
        return Response({"detail": "No existe ese curso en el colegio activo."}, status=400)
    if not curso or not fecha:
        return Response({"detail": "Faltan curso y/o fecha"}, status=400)

    if not _can_manage_course_attendance(
        request.user,
        curso,
        school=active_school,
        school_course=school_course_ref,
    ):
        return Response({"detail": "No tenés permisos para ese curso."}, status=403)

    alumnos = _alumnos_por_curso_qs(
        curso,
        school=active_school,
        school_course=school_course_ref,
    )
    qs = scope_queryset_to_school(Asistencia.objects.filter(alumno__in=alumnos, fecha=fecha), active_school)
    if tipo:
        qs = qs.filter(tipo_asistencia=tipo)

    items = []
    for a in qs.select_related("alumno", "alumno__school_course"):
        items.append(_serialize_asistencia_item(a, curso=curso, school=active_school))

    response_payload = {
        "curso_label": _curso_label(curso, school=active_school),
        "fecha": str(fecha),
        "tipo_asistencia": tipo or None,
        "items": items,
    }
    response_payload.update(
        _public_course_payload(school_course=school_course_ref, curso=curso, school=active_school)
    )
    return Response(response_payload)
