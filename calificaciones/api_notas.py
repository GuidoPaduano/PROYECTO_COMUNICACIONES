# calificaciones/api_notas.py
from __future__ import annotations

from typing import Optional

from django.utils import timezone

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .contexto import resolve_alumno_for_user
from .course_access import course_ref_matches, get_assignment_course_refs
from .jwt_auth import CookieJWTAuthentication as JWTAuthentication
from .models import Alumno, Nota
from .schools import get_request_school, scope_queryset_to_school
from .serializers import NotaPublicSerializer
from .user_groups import get_user_group_names

try:
    from .models_preceptores import PreceptorCurso, ProfesorCurso  # type: ignore
except Exception:
    PreceptorCurso = None
    ProfesorCurso = None


def _has_model_field(model, name: str) -> bool:
    try:
        model._meta.get_field(name)
        return True
    except Exception:
        return False


def _alumno_base_qs(*, school=None):
    return scope_queryset_to_school(
        Alumno.objects.select_related("school", "school_course"),
        school,
    )


def _nota_course_refs_for_user(user, *, school=None, role: str = ""):
    school_id = getattr(school, "id", None) or 0
    cache_attr = "_cached_nota_course_refs_by_scope"
    cache_key = (str(role or "").strip().lower(), school_id)
    cached = getattr(user, cache_attr, None)
    if isinstance(cached, dict) and cache_key in cached:
        return list(cached[cache_key])

    refs = []
    model = None
    user_field = ""
    if cache_key[0] == "preceptor":
        model = PreceptorCurso
        user_field = "preceptor"
    elif cache_key[0] == "profesor":
        model = ProfesorCurso
        user_field = "profesor"

    if model is not None and user_field:
        try:
            qs = scope_queryset_to_school(model.objects.filter(**{user_field: user}), school)
            refs = get_assignment_course_refs(qs)
        except Exception:
            refs = []

    try:
        if not isinstance(cached, dict):
            cached = {}
        cached[cache_key] = tuple(refs)
        setattr(user, cache_attr, cached)
    except Exception:
        pass

    return refs


def _preceptor_can_access_alumno(user, alumno: Alumno) -> bool:
    if PreceptorCurso is None:
        return False

    try:
        school_ref = getattr(alumno, "school", None)
        refs = _nota_course_refs_for_user(user, school=school_ref, role="preceptor")
        return course_ref_matches(refs, obj=alumno)
    except Exception:
        return False


def _profesor_can_access_alumno(user, alumno: Alumno) -> bool:
    if ProfesorCurso is None:
        return False

    try:
        school_ref = getattr(alumno, "school", None)
        refs = _nota_course_refs_for_user(user, school=school_ref, role="profesor")
        return course_ref_matches(refs, obj=alumno)
    except Exception:
        return False


def _authorize_alumno(request, alumno: Alumno) -> bool:
    user = request.user

    if getattr(user, "is_superuser", False):
        return True

    group_names = set(get_user_group_names(user))

    if group_names.intersection({"Directivos", "Directivo"}):
        return True

    if "Profesores" in group_names:
        return _profesor_can_access_alumno(user, alumno)

    if "Preceptores" in group_names:
        return _preceptor_can_access_alumno(user, alumno)

    if getattr(alumno, "padre_id", None) == user.id:
        return True

    if getattr(alumno, "usuario_id", None) == user.id:
        return True

    try:
        resolved = resolve_alumno_for_user(user, school=getattr(alumno, "school", None))
        if resolved.alumno and resolved.alumno.id == alumno.id:
            return True
    except Exception:
        pass

    return False


def _notas_response(alumno: Alumno):
    qs = scope_queryset_to_school(Nota.objects.filter(alumno=alumno), getattr(alumno, "school", None))

    if _has_model_field(Nota, "fecha"):
        qs = qs.order_by("cuatrimestre", "fecha", "materia")
    else:
        qs = qs.order_by("cuatrimestre", "materia")

    data = NotaPublicSerializer(qs, many=True).data
    return Response(
        {
            "alumno": {"id": alumno.id, "id_alumno": alumno.id_alumno, "nombre": alumno.nombre},
            "notas": data,
        }
    )


def _authorize_padre_or_admin(request, alumno: Alumno) -> bool:
    user = request.user
    if getattr(user, "is_superuser", False):
        return True
    return getattr(alumno, "padre_id", None) == user.id


def _get_alumno_from_query_params(request) -> Optional[Alumno]:
    alumno_param = (request.GET.get("alumno") or "").strip()
    alumno_id = (request.GET.get("alumno_id") or "").strip()
    id_alumno = (request.GET.get("id_alumno") or "").strip()
    active_school = get_request_school(request)
    alumno_qs = _alumno_base_qs(school=active_school)

    if alumno_param:
        if alumno_param.isdigit():
            return alumno_qs.get(pk=int(alumno_param))
        return alumno_qs.get(id_alumno=str(alumno_param))

    if id_alumno:
        return alumno_qs.get(id_alumno=str(id_alumno))

    if alumno_id:
        if alumno_id.isdigit():
            return alumno_qs.get(pk=int(alumno_id))
        return alumno_qs.get(id_alumno=str(alumno_id))

    return None


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def notas_listar(request):
    try:
        alumno = _get_alumno_from_query_params(request)
        if alumno is None:
            return Response({"detail": "Falta alumno, alumno_id o id_alumno"}, status=400)
    except Alumno.DoesNotExist:
        return Response({"detail": "Alumno no encontrado"}, status=404)

    if not _authorize_alumno(request, alumno):
        return Response({"detail": "No autorizado"}, status=403)

    return _notas_response(alumno)


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def notas_por_codigo(request, id_alumno: str):
    active_school = get_request_school(request)
    try:
        alumno = _alumno_base_qs(school=active_school).get(id_alumno=str(id_alumno))
    except Alumno.DoesNotExist:
        return Response({"detail": "Alumno no encontrado"}, status=404)

    if not _authorize_alumno(request, alumno):
        return Response({"detail": "No autorizado"}, status=403)

    return _notas_response(alumno)


@api_view(["GET", "POST", "PATCH"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def firmar_nota(request, pk: int):
    active_school = get_request_school(request)
    try:
        nota = scope_queryset_to_school(
            Nota.objects.select_related("alumno"),
            active_school,
        ).get(pk=pk)
    except Nota.DoesNotExist:
        return Response({"detail": "Nota no encontrada"}, status=404)

    if not _authorize_padre_or_admin(request, nota.alumno):
        return Response({"detail": "No autorizado"}, status=403)

    if request.method == "GET":
        return Response(
            {
                "id": nota.id,
                "alumno_id": nota.alumno_id,
                "firmada": bool(getattr(nota, "firmada", False)),
                "firmada_en": nota.firmada_en.isoformat() if getattr(nota, "firmada_en", None) else None,
            }
        )

    if bool(getattr(nota, "firmada", False)):
        return Response(
            {
                "detail": "La nota ya fue firmada.",
                "id": nota.id,
                "alumno_id": nota.alumno_id,
                "firmada": True,
                "firmada_en": nota.firmada_en.isoformat() if getattr(nota, "firmada_en", None) else None,
            },
            status=400,
        )

    nota.firmada = True
    nota.firmada_en = timezone.now()
    nota.firmada_por = request.user
    nota.save(update_fields=["firmada", "firmada_en", "firmada_por"])

    return Response(
        {
            "id": nota.id,
            "alumno_id": nota.alumno_id,
            "firmada": True,
            "firmada_en": nota.firmada_en.isoformat() if nota.firmada_en else None,
        }
    )
