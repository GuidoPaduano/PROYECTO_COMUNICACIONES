# calificaciones/views/_mensajes_html.py
# Vistas HTML para mensajería: enviar_mensaje, enviar_comunicado, ver_mensajes

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render

from ..models import Alumno, Mensaje, Notificacion
from ..schools import (
    get_request_school,
    scope_queryset_to_school,
)
from ._acceso import (
    _has_model_field,
    _has_role,
    _mensaje_recipient_field,
    _mensaje_sender_field,
    _profesor_assignment_refs,
    _resolve_request_course_selection,
    _school_course_options_for_ui,
)
from ..course_access import course_ref_matches, filter_course_options_by_refs
from ._cursos import _alumnos_por_curso_qs
from ._notificaciones import _notification_course_meta


@login_required
def enviar_mensaje(request):
    if not (_has_role(request, 'Profesores') or request.user.is_superuser):
        return HttpResponse("No tenés permiso.", status=403)

    active_school = get_request_school(request)
    cursos_disponibles = _school_course_options_for_ui(school=active_school)
    selected_course = _resolve_request_course_selection(
        request,
        school=active_school,
        required=False,
    )
    if selected_course["error"]:
        return HttpResponse(selected_course["error"], status=400)
    curso_seleccionado = selected_course["course_code"]
    curso_seleccionado_id = selected_course["school_course_id"]
    if _has_role(request, "Profesores") and not request.user.is_superuser:
        assigned_refs = _profesor_assignment_refs(request.user, school=active_school)
        if assigned_refs:
            cursos_disponibles = filter_course_options_by_refs(cursos_disponibles, assigned_refs)
            if (curso_seleccionado_id or curso_seleccionado) and not course_ref_matches(
                assigned_refs,
                school_course_id=curso_seleccionado_id,
                course_code=curso_seleccionado,
            ):
                return HttpResponse("No tenés permiso para ese curso.", status=403)
    alumnos = _alumnos_por_curso_qs(curso_seleccionado, school=active_school) if curso_seleccionado else []

    if request.method == 'POST':
        alumno_id = request.POST['alumno']
        asunto = request.POST['asunto']
        contenido = request.POST['contenido']
        try:
            alumno = scope_queryset_to_school(Alumno.objects.all(), active_school).get(id=int(alumno_id))
        except Exception:
            alumno = scope_queryset_to_school(Alumno.objects.all(), active_school).get(id_alumno=alumno_id)
        receptor = alumno.padre

        if receptor:
            sf = _mensaje_sender_field()
            rf = _mensaje_recipient_field()

            kwargs = {
                sf: request.user,
                rf: receptor,
                "asunto": asunto,
                "contenido": contenido,
                "school": active_school or getattr(alumno, "school", None),
            }
            if _has_model_field(Mensaje, "school_course") and getattr(alumno, "school_course", None) is not None:
                kwargs["school_course"] = getattr(alumno, "school_course", None)
            if getattr(alumno, "curso", None):
                kwargs["curso"] = getattr(alumno, "curso", None)

            msg = Mensaje.objects.create(**kwargs)
            try:
                contenido_corto = (contenido[:160] + "...") if len(contenido) > 160 else contenido
                url = "/mensajes"
                if hasattr(msg, "thread_id") and getattr(msg, "thread_id", None):
                    url = f"/mensajes/hilo/{getattr(msg, 'thread_id')}"
                actor_label = (request.user.get_full_name() or request.user.username or "Usuario").strip()
                titulo = f"{actor_label}: {asunto}" if asunto else f"Nuevo mensaje de {actor_label}"
                Notificacion.objects.create(
                    school=active_school or getattr(alumno, "school", None),
                    destinatario=receptor,
                    tipo="mensaje",
                    titulo=titulo,
                    descripcion=contenido_corto.strip() or None,
                    url=url,
                    leida=False,
                    meta={
                        "mensaje_id": getattr(msg, "id", None),
                        "thread_id": str(getattr(msg, "thread_id", "")) if hasattr(msg, "thread_id") else str(getattr(msg, "id", "")),
                        **_notification_course_meta(
                            alumno=alumno,
                            school_course=getattr(msg, "school_course", None),
                            course_code=getattr(alumno, "curso", "") if alumno else "",
                            school=active_school,
                        ),
                        "remitente_id": getattr(request.user, "id", None),
                        "alumno_id": getattr(alumno, "id", None) if alumno else None,
                    },
                )
            except Exception:
                pass
            return redirect('index')
        else:
            return HttpResponse("Este alumno no tiene padre asignado.", status=400)

    return render(request, 'calificaciones/enviar_mensaje.html', {
        'cursos': cursos_disponibles,
        'curso_seleccionado': curso_seleccionado,
        'curso_seleccionado_id': curso_seleccionado_id,
        'alumnos': alumnos
    })


@login_required
def enviar_comunicado(request):
    if not (_has_role(request, 'Profesores') or request.user.is_superuser):
        return HttpResponse("No tenés permiso.", status=403)

    active_school = get_request_school(request)
    cursos = _school_course_options_for_ui(school=active_school)
    if _has_role(request, "Profesores") and not request.user.is_superuser:
        assigned_refs = _profesor_assignment_refs(request.user, school=active_school)
        if assigned_refs:
            cursos = filter_course_options_by_refs(cursos, assigned_refs)

    if request.method == 'POST':
        selected_course = _resolve_request_course_selection(
            request,
            school=active_school,
            required=True,
        )
        if selected_course["error"]:
            return HttpResponse(selected_course["error"], status=400)
        curso = selected_course["course_code"]
        curso_id = selected_course["school_course_id"]
        if _has_role(request, "Profesores") and not request.user.is_superuser:
            assigned_refs = _profesor_assignment_refs(request.user, school=active_school)
            if assigned_refs and not course_ref_matches(
                assigned_refs,
                school_course_id=curso_id,
                course_code=curso,
            ):
                return HttpResponse("No tenés permiso para ese curso.", status=403)
        asunto = request.POST['asunto']
        contenido = request.POST['contenido']
        alumnos = scope_queryset_to_school(Alumno.objects.all(), active_school).filter(
            school_course_id=curso_id,
            padre__isnull=False,
        )

        sf = _mensaje_sender_field()
        rf = _mensaje_recipient_field()

        notifs = []
        for alumno in alumnos:
            kwargs = {
                sf: request.user,
                rf: alumno.padre,
                "asunto": asunto,
                "contenido": contenido,
                "school": active_school or getattr(alumno, "school", None),
            }
            if _has_model_field(Mensaje, "school_course") and getattr(alumno, "school_course", None) is not None:
                kwargs["school_course"] = getattr(alumno, "school_course", None)
            kwargs["curso"] = curso
            msg = Mensaje.objects.create(**kwargs)
            try:
                contenido_corto = (contenido[:160] + "...") if len(contenido) > 160 else contenido
                url = "/mensajes"
                if hasattr(msg, "thread_id") and getattr(msg, "thread_id", None):
                    url = f"/mensajes/hilo/{getattr(msg, 'thread_id')}"
                actor_label = (request.user.get_full_name() or request.user.username or "Usuario").strip()
                titulo = f"{actor_label}: {asunto}" if asunto else f"Nuevo mensaje de {actor_label}"
                notifs.append(
                    Notificacion(
                        school=active_school or getattr(alumno, "school", None),
                        destinatario=alumno.padre,
                        tipo="mensaje",
                        titulo=titulo,
                        descripcion=contenido_corto.strip() or None,
                        url=url,
                        leida=False,
                        meta={
                            "mensaje_id": getattr(msg, "id", None),
                            "thread_id": str(getattr(msg, "thread_id", "")) if hasattr(msg, "thread_id") else str(getattr(msg, "id", "")),
                            **_notification_course_meta(
                                alumno=alumno,
                                school_course=getattr(msg, "school_course", None),
                                course_code=curso,
                                school=active_school,
                            ),
                            "remitente_id": getattr(request.user, "id", None),
                            "alumno_id": getattr(alumno, "id", None),
                        },
                    )
                )
            except Exception:
                pass

        if notifs:
            try:
                Notificacion.objects.bulk_create(notifs)
            except Exception:
                pass

        return redirect('index')

    selected_course = _resolve_request_course_selection(
        request,
        school=active_school,
        required=False,
    )
    if selected_course["error"]:
        return HttpResponse(selected_course["error"], status=400)
    return render(request, 'calificaciones/enviar_comunicado.html', {
        'cursos': cursos,
        'curso_seleccionado_id': selected_course["school_course_id"],
    })

@login_required
def ver_mensajes(request):
    """
    Lista los mensajes recibidos por el usuario autenticado (padre/tutor).
    Evita usar campos inexistentes y ordena por 'fecha_envio' si existe.
    """
    if _has_role(request, 'Padres') or request.user.is_superuser:
        active_school = get_request_school(request)
        order_field = 'fecha_envio' if _has_model_field(Mensaje, 'fecha_envio') else 'id'

        rf = _mensaje_recipient_field()
        mensajes = scope_queryset_to_school(
            Mensaje.objects.filter(**{rf: request.user}),
            active_school,
        ).order_by(f'-{order_field}')
        select_fields = [_mensaje_sender_field(), _mensaje_recipient_field()]
        if _has_model_field(Mensaje, "school_course"):
            select_fields.append("school_course")
        mensajes = mensajes.select_related(*select_fields)

        return render(request, 'calificaciones/ver_mensajes.html', {'mensajes': mensajes})
    else:
        return HttpResponse("No tienes permiso para ver mensajes.", status=403)
