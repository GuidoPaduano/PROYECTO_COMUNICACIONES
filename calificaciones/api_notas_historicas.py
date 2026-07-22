from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Nota
from .schools import get_request_school, scope_queryset_to_school
from .api_admin_staff._helpers import _require_school_admin


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def notas_historicas(request):
    denied = _require_school_admin(request)
    if denied is not None:
        return denied

    active_school = get_request_school(request)
    if active_school is None:
        return Response({"detail": "No se pudo determinar el colegio activo."}, status=400)

    anio_lectivo = request.GET.get("anio_lectivo", "").strip()
    school_course_id = request.GET.get("school_course_id", "").strip()

    if not anio_lectivo:
        return Response({"detail": "Parámetro anio_lectivo requerido."}, status=400)

    try:
        anio_lectivo = int(anio_lectivo)
    except ValueError:
        return Response({"detail": "anio_lectivo debe ser un número."}, status=400)

    # Años disponibles para el selector
    if request.GET.get("available_years"):
        years = (
            scope_queryset_to_school(
                Nota.objects.filter(es_final=True, anio_lectivo__isnull=False),
                active_school,
            )
            .values_list("anio_lectivo", flat=True)
            .distinct()
            .order_by("-anio_lectivo")
        )
        return Response({"years": list(years)})

    qs = scope_queryset_to_school(
        Nota.objects.filter(es_final=True, anio_lectivo=anio_lectivo).select_related("alumno"),
        active_school,
    )

    if school_course_id:
        try:
            qs = qs.filter(alumno__school_course_id=int(school_course_id))
        except ValueError:
            pass

    notas = list(qs.order_by("alumno__apellido", "alumno__nombre", "alumno__id"))

    # Construir índice: alumno_id → {materia → {cuatrimestre → nota}}
    alumnos_map = {}
    materias_set = []

    for nota in notas:
        alumno = nota.alumno
        aid = alumno.id
        if aid not in alumnos_map:
            alumnos_map[aid] = {
                "id": alumno.id,
                "nombre": alumno.nombre,
                "apellido": alumno.apellido,
                "id_alumno": alumno.id_alumno,
                "notas": {},
            }
        mat = nota.materia
        if mat not in alumnos_map[aid]["notas"]:
            alumnos_map[aid]["notas"][mat] = {}
        alumnos_map[aid]["notas"][mat][str(nota.cuatrimestre)] = {
            "calificacion": nota.calificacion,
            "nota_numerica": str(nota.nota_numerica) if nota.nota_numerica is not None else None,
            "resultado": nota.resultado,
        }
        if mat not in materias_set:
            materias_set.append(mat)

    materias_set.sort()

    return Response({
        "anio_lectivo": anio_lectivo,
        "materias": materias_set,
        "alumnos": list(alumnos_map.values()),
    })
