# calificaciones/views/_boletin.py
# Boletín PDF e historial de notas

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

from reportlab.pdfgen import canvas

from ..models import Alumno, Nota
from ..schools import (
    get_request_school,
    scope_queryset_to_school,
)
from ._acceso import (
    _can_access_alumno_data,
    _effective_groups,
    _get_preview_role,
    _has_role,
    _profesor_can_access_alumno,
)


@login_required
def generar_boletin_pdf(request, alumno_id):
    active_school = get_request_school(request)
    alumno = get_object_or_404(
        scope_queryset_to_school(Alumno.objects.select_related("school", "school_course"), active_school),
        id_alumno=alumno_id,
    )
    if not _can_access_alumno_data(request, alumno):
        return HttpResponse("No tenés permiso para ver este boletín.", status=403)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="boletin_{alumno.nombre}.pdf'
    p = canvas.Canvas(response)
    p.drawString(100, 800, f"Boletín de {alumno.nombre}")
    y = 750
    notas = scope_queryset_to_school(Nota.objects.filter(alumno=alumno), active_school).order_by('cuatrimestre')
    for nota in notas:
        p.drawString(100, y, f"{nota.materia} - Cuatrimestre {nota.cuatrimestre}: {nota.calificacion}")
        y -= 20
    p.showPage()
    p.save()
    return response


@login_required
def historial_notas_profesor(request, alumno_id):
    if not (_has_role(request, 'Profesores') or request.user.is_superuser):
        return HttpResponse("No tenés permiso para ver esto.", status=403)

    active_school = get_request_school(request)
    alumno = get_object_or_404(scope_queryset_to_school(Alumno.objects.all(), active_school), id_alumno=alumno_id)
    viewer_groups = set(_effective_groups(request))
    if "Profesores" in viewer_groups and not request.user.is_superuser:
        if not _profesor_can_access_alumno(request.user, alumno):
            return HttpResponse("No tenés permiso para ese curso.", status=403)
    notas_base_qs = scope_queryset_to_school(Nota.objects.filter(alumno=alumno), active_school)
    materias = set(notas_base_qs.values_list('materia', flat=True))
    materia_seleccionada = request.GET.get('materia')
    notas = []

    if materia_seleccionada:
        notas = notas_base_qs.filter(materia=materia_seleccionada).order_by('cuatrimestre')

    return render(request, 'calificaciones/historial_notas.html', {
        'alumno': alumno,
        'materias': materias,
        'materia_seleccionada': materia_seleccionada,
        'notas': notas
    })


@login_required
def historial_notas_padre(request):
    if not (_has_role(request, 'Padres') or request.user.is_superuser):
        return HttpResponse("No tenés permiso para ver esto.", status=403)

    active_school = get_request_school(request)
    alumnos_qs = scope_queryset_to_school(
        Alumno.objects.select_related("school_course"),
        active_school,
    )
    alumnos = alumnos_qs.filter(padre=request.user)
    if not alumnos.exists() and _get_preview_role(request):
        a0 = alumnos_qs.filter(padre__isnull=False).order_by('padre_id').first()
        if a0 and a0.padre_id:
            alumnos = alumnos_qs.filter(padre_id=a0.padre_id)
    alumno = alumnos.first()

    notas_base_qs = scope_queryset_to_school(Nota.objects.filter(alumno=alumno), active_school) if alumno else Nota.objects.none()
    materias = set(notas_base_qs.values_list('materia', flat=True)) if alumno else set()
    materia_seleccionada = request.GET.get('materia')
    notas = []

    if materia_seleccionada and alumno:
        notas = notas_base_qs.filter(materia=materia_seleccionada).order_by('cuatrimestre')

    return render(request, 'calificaciones/historial_notas.html', {
        'alumno': alumno,
        'materias': materias,
        'materia_seleccionada': materia_seleccionada,
        'notas': notas
    })
