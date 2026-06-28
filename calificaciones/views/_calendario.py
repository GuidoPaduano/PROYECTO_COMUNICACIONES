# calificaciones/views/_calendario.py
# Vistas HTML para el calendario de eventos

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from ..models import Evento
from ..schools import (
    get_request_school,
    scope_queryset_to_school,
)
from ._acceso import (
    _has_role,
    _profesor_assignment_refs,
    _resolve_request_course_selection,
    EventoForm,
)
from ..course_access import course_ref_matches


@login_required
def calendario_view(request):
    form = EventoForm(school=get_request_school(request))
    return render(request, 'calificaciones/calendario.html', {'form': form})


@login_required
def crear_evento(request):
    if not (_has_role(request, 'Profesores') or request.user.is_superuser):
        return HttpResponse("No tenés permiso para crear eventos.", status=403)

    active_school = get_request_school(request)
    assigned_refs = []
    if _has_role(request, "Profesores") and not request.user.is_superuser:
        assigned_refs = _profesor_assignment_refs(request.user, school=active_school)

    if request.method == 'POST':
        form = EventoForm(request.POST, school=active_school)
        if assigned_refs:
            selected_course = _resolve_request_course_selection(
                request,
                school=active_school,
                required=True,
            )
            if selected_course["error"]:
                return JsonResponse({"detail": selected_course["error"]}, status=400)
            if not course_ref_matches(
                assigned_refs,
                school_course_id=selected_course["school_course_id"],
                course_code=selected_course["course_code"],
            ):
                return JsonResponse({"detail": "No autorizado para ese curso."}, status=403)
        if form.is_valid():
            evento = form.save(commit=False)
            evento.creado_por = request.user
            evento.school = active_school
            evento.save()
            try:
                from ..api_eventos import _notify_evento_creado
                _notify_evento_creado(request, evento)
            except Exception:
                pass
            return JsonResponse({"id": evento.id})
        else:
            return JsonResponse({"errors": form.errors}, status=400)

    return JsonResponse({"detail": "Metodo no permitido"}, status=405)


@login_required
def editar_evento(request, evento_id):
    active_school = get_request_school(request)
    evento = get_object_or_404(scope_queryset_to_school(Evento.objects.all(), active_school), id=evento_id)
    evento_owner = getattr(evento, "creado_por", None)

    if not (request.user == evento_owner or request.user.is_superuser):
        return HttpResponse("No tenés permiso para editar este evento.", status=403)

    if request.method == 'POST':
        form = EventoForm(request.POST, instance=evento, school=active_school)
        if _has_role(request, "Profesores") and not request.user.is_superuser:
            assigned_refs = _profesor_assignment_refs(request.user, school=active_school)
            if assigned_refs:
                selected_course = _resolve_request_course_selection(
                    request,
                    school=active_school,
                    required=True,
                )
                if selected_course["error"]:
                    return JsonResponse({"detail": selected_course["error"]}, status=400)
                if not course_ref_matches(
                    assigned_refs,
                    school_course_id=selected_course["school_course_id"],
                    course_code=selected_course["course_code"],
                ):
                    return JsonResponse({"detail": "No autorizado para ese curso."}, status=403)
        if form.is_valid():
            evento = form.save()
            return JsonResponse({"id": evento.id})
        else:
            return JsonResponse({"errors": form.errors}, status=400)
    else:
        form = EventoForm(instance=evento, school=active_school)
        return render(request, 'calificaciones/parcial_editar_evento.html', {'form': form, 'evento': evento})


@login_required
def eliminar_evento(request, evento_id):
    active_school = get_request_school(request)
    evento = get_object_or_404(scope_queryset_to_school(Evento.objects.all(), active_school), id=evento_id)
    evento_owner = getattr(evento, "creado_por", None)

    if not (request.user == evento_owner or request.user.is_superuser):
        return HttpResponse("No tenés permiso para eliminar este evento.", status=403)

    if request.method == 'POST':
        evento.delete()
        return redirect('calendario')

    return render(request, 'calificaciones/confirmar_eliminar_evento.html', {'evento': evento})
