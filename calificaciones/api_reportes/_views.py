from __future__ import annotations

from django.core.cache import cache

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..contexto import resolve_alumno_for_user
from ..course_access import course_ref_matches
from ..jwt_auth import CookieJWTAuthentication as JWTAuthentication
from ..models import Alumno, Nota
from ..schools import get_request_school, scope_queryset_to_school

from ._helpers import (
    _active_school_id,
    _apply_anio_filter,
    _apply_cuatrimestre_filter,
    _apply_materia_filter,
    _available_course_codes,
    _build_alumno_historico_payload,
    _build_notas_payload,
    _filter_notas_por_curso,
    _mis_estadisticas_cache_key,
    _normalize_anio,
    _normalize_cuatrimestre,
    _normalize_materia_filter,
    _public_course_payload,
    _resolve_materia,
    _resolve_path_course_selection,
    _resolve_preceptor_course_refs,
    _resolve_preceptor_cursos,
    _resolve_profesor_course_refs,
    _resolve_profesor_cursos,
    _resolve_reporte_alumno_en_curso,
    _role_label,
    _serialize_alumno,
)


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def reportes_mis_estadisticas(request):
    user = request.user
    role = _role_label(user)
    cuatrimestre = _normalize_cuatrimestre(request.GET.get("cuatrimestre"))
    anio = _normalize_anio(request.GET.get("anio"))
    materia = _normalize_materia_filter(request.GET.get("materia"))
    active_school = get_request_school(request)
    alumno_param = (request.GET.get("alumno_id") or "").strip()

    if role not in ("Padres", "Alumnos", "Superuser"):
        return Response({"detail": "No autorizado para este reporte."}, status=403)

    cache_key = _mis_estadisticas_cache_key(
        user_id=getattr(user, "id", None),
        role=role,
        school_id=getattr(active_school, "id", None),
        alumno_param=alumno_param,
        anio=anio,
        cuatrimestre=cuatrimestre,
        materia=materia,
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return Response(cached)

    alumnos = []
    selected = None

    if role == "Superuser":
        if not alumno_param:
            return Response({"detail": "Para superusuario envia ?alumno_id=<id o legajo>."}, status=400)
        alumnos_qs = scope_queryset_to_school(
            Alumno.objects.select_related("school_course"),
            active_school,
        )
        if alumno_param.isdigit():
            selected = alumnos_qs.filter(id=int(alumno_param)).first()
        else:
            selected = alumnos_qs.filter(id_alumno__iexact=alumno_param).first()
        if not selected:
            return Response({"detail": "Alumno no encontrado."}, status=404)
        alumnos = [selected]

    elif role == "Padres":
        alumnos_qs = (
            scope_queryset_to_school(
                Alumno.objects.select_related("school_course"),
                active_school,
            )
            .filter(padre=user)
            .order_by("curso", "nombre")
        )
        alumnos = list(alumnos_qs)
        if not alumnos:
            payload = {
                "scope": "mis_estadisticas",
                "rol": role,
                "alumnos": [],
                "alumno_activo": None,
                "resumen_notas": {
                    "total_evaluaciones": 0,
                    "conteos_por_estado": {"TEA": 0, "TEP": 0, "TED": 0},
                    "porcentajes_por_estado": {"TEA": 0.0, "TEP": 0.0, "TED": 0.0},
                },
                "por_materia": [],
                "evolucion_mensual_notas": [],
                "materia_mas_floja": None,
            }
            cache.set(cache_key, payload, 120)
            return Response(payload)

        if not alumno_param:
            selected = alumnos[0]
        elif alumno_param.isdigit():
            selected = alumnos_qs.filter(id=int(alumno_param)).first()
        else:
            selected = alumnos_qs.filter(id_alumno__iexact=alumno_param).first()

        if not selected:
            return Response({"detail": "No autorizado para ese alumno."}, status=403)

    else:  # Alumnos
        resolution = resolve_alumno_for_user(user, school=active_school)
        selected = resolution.alumno
        if not selected:
            return Response({"detail": "No se pudo resolver el alumno asociado al usuario."}, status=404)
        alumnos = [selected]

    notas_qs = scope_queryset_to_school(Nota.objects.filter(alumno=selected), active_school)
    notas_qs = _apply_anio_filter(notas_qs, anio)
    notas_qs = _apply_cuatrimestre_filter(notas_qs, cuatrimestre)
    notas_qs = _apply_materia_filter(notas_qs, materia)

    notas_payload = _build_notas_payload(notas_qs)

    payload = {
        "scope": "mis_estadisticas",
        "rol": role,
        "alumnos": [_serialize_alumno(a) for a in alumnos],
        "alumno_activo": _serialize_alumno(selected),
        "filtros": {"cuatrimestre": cuatrimestre, "anio": anio, "materia": materia},
        **notas_payload,
    }
    cache.set(cache_key, payload, 120)
    return Response(payload)


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def reportes_por_curso(request, curso: str):
    user = request.user
    role = _role_label(user)
    active_school = get_request_school(request)
    school_course, curso_norm, course_error = _resolve_path_course_selection(
        curso,
        school=active_school,
    )
    anio = _normalize_anio(request.GET.get("anio"))
    cuatrimestre = _normalize_cuatrimestre(request.GET.get("cuatrimestre"))
    materia = _normalize_materia_filter(request.GET.get("materia"))
    alumno_param = (request.GET.get("alumno_id") or "").strip()

    if course_error:
        return Response({"detail": course_error}, status=400)

    if role not in ("Profesores", "Preceptores", "Directivos", "Superuser"):
        return Response({"detail": "No autorizado para este reporte."}, status=403)

    if role == "Profesores":
        cursos_habilitados = _resolve_profesor_cursos(user, school=active_school)
        course_refs = _resolve_profesor_course_refs(user, school=active_school)
    elif role == "Directivos":
        cursos_habilitados = sorted(set(_available_course_codes(active_school)))
        course_refs = []
    elif role == "Preceptores":
        cursos_habilitados = _resolve_preceptor_cursos(user, school=active_school)
        course_refs = _resolve_preceptor_course_refs(user, school=active_school)
    else:
        cursos_habilitados = sorted(set(_available_course_codes(active_school)))
        course_refs = []

    # Permiso estricto: si no hay cursos asignados, se deniega.
    if not cursos_habilitados:
        return Response({"detail": "No tenés cursos asignados."}, status=403)

    if course_refs and not course_ref_matches(
        course_refs,
        school_course_id=getattr(school_course, "id", None),
        course_code=curso_norm,
    ):
        return Response({"detail": "No autorizado para ese curso."}, status=403)

    cache_key = (
        f"reportes:v2:curso:u{user.id}:r{role}:s{_active_school_id(active_school)}:"
        f"c{curso_norm}:a{alumno_param or 'all'}:y{anio or 'all'}:q{cuatrimestre or 'all'}:m{materia or 'all'}"
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return Response(cached)

    notas_qs_base = _filter_notas_por_curso(
        scope_queryset_to_school(Nota.objects.all(), active_school),
        curso_norm,
        school=active_school,
        school_course=school_course,
    )
    notas_qs = _apply_anio_filter(notas_qs_base, anio)
    notas_qs = _apply_cuatrimestre_filter(notas_qs, cuatrimestre)
    notas_qs = _apply_materia_filter(notas_qs, materia)

    if alumno_param:
        alumno, alumno_error = _resolve_reporte_alumno_en_curso(
            raw_alumno=alumno_param,
            curso=curso_norm,
            school=active_school,
            school_course=school_course,
        )
        if alumno_error:
            status_code = 404 if alumno_error == "Alumno no encontrado." else 400
            return Response({"detail": alumno_error}, status=status_code)

        payload = _build_alumno_historico_payload(
            alumno=alumno,
            notas_qs=notas_qs.filter(alumno=alumno),
            notas_qs_historicas=_apply_materia_filter(
                _apply_cuatrimestre_filter(notas_qs_base.filter(alumno=alumno), cuatrimestre),
                materia,
            ),
            role=role,
            school=active_school,
            curso=curso_norm,
            school_course=school_course,
            cuatrimestre=cuatrimestre,
            anio=anio,
            materia=materia,
        )
        payload["permisos"] = {"cursos_habilitados": cursos_habilitados}
        cache.set(cache_key, payload, 120)
        return Response(payload)

    notas_payload = _build_notas_payload(notas_qs)

    payload = {
        "scope": "curso",
        "rol": role,
        **_public_course_payload(school=active_school, course_code=curso_norm, school_course=school_course),
        "filtros": {"cuatrimestre": cuatrimestre, "anio": anio, "materia": materia},
        "permisos": {"cursos_habilitados": cursos_habilitados},
        **notas_payload,
    }

    cache.set(cache_key, payload, 120)
    return Response(payload)


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def reportes_materia_curso(request, id_materia: str, curso: str):
    user = request.user
    role = _role_label(user)
    active_school = get_request_school(request)
    school_course, curso_norm, course_error = _resolve_path_course_selection(
        curso,
        school=active_school,
    )
    cuatrimestre = _normalize_cuatrimestre(request.GET.get("cuatrimestre"))

    if course_error:
        return Response({"detail": course_error}, status=400)

    if role not in ("Profesores", "Superuser"):
        return Response({"detail": "Solo profesores pueden acceder a este reporte."}, status=403)

    materia = _resolve_materia(id_materia)
    if not materia:
        return Response({"detail": "Materia inválida."}, status=404)

    if role != "Superuser":
        cursos_habilitados = _resolve_profesor_cursos(user, school=active_school)
        course_refs = _resolve_profesor_course_refs(user, school=active_school)
        if not cursos_habilitados:
            return Response({"detail": "No tenés cursos asignados."}, status=403)
        if course_refs and not course_ref_matches(
            course_refs,
            school_course_id=getattr(school_course, "id", None),
            course_code=curso_norm,
        ):
            return Response({"detail": "No autorizado para ese curso."}, status=403)
    else:
        cursos_habilitados = sorted(set(_available_course_codes(active_school)))

    cache_key = (
        f"reportes:v2:materia_curso:u{user.id}:r{role}:s{_active_school_id(active_school)}:c{curso_norm}:m{materia}:q{cuatrimestre or 'all'}"
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return Response(cached)

    notas_qs = _filter_notas_por_curso(
        scope_queryset_to_school(Nota.objects.all(), active_school),
        curso_norm,
        school=active_school,
        school_course=school_course,
    ).filter(materia=materia)
    notas_qs = _apply_cuatrimestre_filter(notas_qs, cuatrimestre)

    notas_payload = _build_notas_payload(notas_qs)

    payload = {
        "scope": "materia_curso",
        "rol": role,
        **_public_course_payload(school=active_school, course_code=curso_norm, school_course=school_course),
        "materia": {"id": id_materia, "nombre": materia},
        "filtros": {"cuatrimestre": cuatrimestre},
        "permisos": {"cursos_habilitados": cursos_habilitados},
        **notas_payload,
    }
    cache.set(cache_key, payload, 120)
    return Response(payload)
