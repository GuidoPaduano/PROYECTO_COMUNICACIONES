# calificaciones/views/_asistencia_html.py
# Vistas HTML para asistencias y perfil de alumno

from datetime import date

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from ..models import Alumno, Asistencia, Notificacion
from ..schools import (
    get_request_school,
    scope_queryset_to_school,
)
from ..utils_cursos import get_course_label
from ._acceso import (
    _effective_groups,
    _has_role,
    _preceptor_assignment_refs,
    _preceptor_can_access_alumno,
    _profesor_can_access_alumno,
    _resolve_request_course_selection,
    _school_course_options_for_ui,
)
from ..course_access import course_ref_matches, filter_course_options_by_refs
from ._cursos import _alumnos_por_curso_qs
from ._notificaciones import (
    _notification_course_meta,
    _notification_course_name,
    _resolver_destinatarios_notif,
)
from ..contexto import resolve_alumno_for_user


@login_required
def pasar_asistencia(request):
    usuario = request.user
    active_school = get_request_school(request)
    alumnos = []
    curso_id = None
    curso_code = None
    school_course_name = None

    if usuario.is_superuser:
        cursos = _school_course_options_for_ui(school=active_school)
        selected_course = _resolve_request_course_selection(
            request,
            school=active_school,
            required=False,
        )
        if selected_course["error"]:
            return render(request, 'calificaciones/error.html', {'mensaje': selected_course["error"]}, status=400)
        curso_id = selected_course["school_course_id"]
        curso_code = selected_course["course_code"]
        if curso_code:
            school_course_name = get_course_label(curso_code, school=active_school)
    else:
        allowed_refs = _preceptor_assignment_refs(usuario, school=active_school)
        if not allowed_refs:
            return render(request, 'calificaciones/error.html', {'mensaje': 'No tenés un curso asignado como preceptor.'})
        cursos = filter_course_options_by_refs(_school_course_options_for_ui(school=active_school), allowed_refs)
        selected_course = _resolve_request_course_selection(
            request,
            school=active_school,
            required=False,
        )
        if selected_course["error"]:
            return render(request, 'calificaciones/error.html', {'mensaje': selected_course["error"]}, status=400)
        if (selected_course["school_course_id"] or selected_course["course_code"]) and not course_ref_matches(
            allowed_refs,
            school_course_id=selected_course["school_course_id"],
            course_code=selected_course["course_code"],
        ):
            return render(request, 'calificaciones/error.html', {'mensaje': 'No tenés permiso para ese curso.'})
        selected_option = None
        if selected_course["school_course_id"]:
            selected_option = next(
                (option for option in cursos if option.get("school_course_id") == selected_course["school_course_id"]),
                None,
            )
        if selected_option is None and selected_course["course_code"]:
            selected_option = next(
                (option for option in cursos if option.get("code") == selected_course["course_code"]),
                None,
            )
        if selected_option is None and cursos:
            selected_option = cursos[0]

        if selected_option is not None:
            curso_id = selected_option.get("school_course_id")
            curso_code = selected_option.get("code")
            school_course_name = selected_option.get("nombre") or get_course_label(curso_code, school=active_school)

    if curso_code:
        alumnos = (
            _alumnos_por_curso_qs(curso_code, school=active_school)
            .select_related("school", "school_course", "padre", "usuario")
            .order_by('nombre')
        )

    if request.method == 'POST':
        fecha_actual = date.today()
        asistencia_objs = []
        ausentes_ids = []
        for alumno in alumnos:
            presente = request.POST.get(f'asistencia_{alumno.id}') == 'on'
            asistencia_objs.append(Asistencia(
                school=active_school or getattr(alumno, "school", None),
                alumno=alumno,
                fecha=fecha_actual,
                presente=presente
            ))
            if not presente:
                ausentes_ids.append(alumno.id)

        Asistencia.objects.filter(alumno__in=alumnos, fecha=fecha_actual).delete()
        Asistencia.objects.bulk_create(asistencia_objs)

        # Notificar inasistencias a padres/alumnos
        try:
            for alumno in alumnos:
                if alumno.id not in ausentes_ids:
                    continue
                destinatarios = _resolver_destinatarios_notif(alumno)
                if not destinatarios:
                    continue
                alumno_nombre = (f"{getattr(alumno, 'apellido', '')} {getattr(alumno, 'nombre', '')}").strip()
                if not alumno_nombre:
                    alumno_nombre = getattr(alumno, "nombre", "") or str(getattr(alumno, "id_alumno", "")) or "Alumno"
                titulo = f"Inasistencia registrada: {alumno_nombre}"
                course_name = _notification_course_name(alumno=alumno)
                descripcion = f"Alumno: {alumno_nombre} · Curso: {course_name or 's/d'} · Fecha: {fecha_actual.isoformat()}"
                for dest in destinatarios:
                    Notificacion.objects.create(
                        school=active_school or getattr(alumno, "school", None),
                        destinatario=dest,
                        tipo="inasistencia",
                        titulo=titulo,
                        descripcion=descripcion,
                        url=f"/alumnos/{getattr(alumno, 'id', '')}/?tab=asistencias",
                        leida=False,
                        meta={
                            "alumno_id": getattr(alumno, "id", None),
                            "alumno_legajo": getattr(alumno, "id_alumno", None),
                            **_notification_course_meta(alumno=alumno, school=active_school),
                            "fecha": fecha_actual.isoformat(),
                            "tipo_asistencia": "clases",
                        },
                    )
        except Exception:
            pass

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({"registradas": len(asistencia_objs)})
        return redirect('index')

    return render(request, 'calificaciones/pasar_asistencia.html', {
        'alumnos': alumnos,
        'curso_id': curso_id,
        'curso_code': curso_code,
        'school_course_name': school_course_name,
        'cursos': cursos
    })


@login_required
def perfil_alumno(request, alumno_id):
    active_school = get_request_school(request)
    alumno = get_object_or_404(
        scope_queryset_to_school(
            Alumno.objects.select_related("school", "school_course", "padre", "usuario"),
            active_school,
        ),
        id_alumno=alumno_id,
    )
    viewer_groups = set(_effective_groups(request))

    is_padre = (request.user == alumno.padre)
    is_prof_ok = ("Profesores" in viewer_groups) and _profesor_can_access_alumno(request.user, alumno)
    is_prof_or_super = (request.user.is_superuser or is_prof_ok)
    # Alumno propio (mismo criterio que en endpoints API)
    is_alumno_mismo = getattr(alumno, "usuario_id", None) == request.user.id
    if not is_alumno_mismo and "Alumnos" in viewer_groups:
        try:
            r = resolve_alumno_for_user(request.user, school=active_school)
            if r.alumno and r.alumno.id == alumno.id:
                is_alumno_mismo = True
        except Exception:
            pass

    # ✅ NUEVO: permitir preceptor si el curso coincide
    is_preceptor_ok = (
        ("Directivos" in viewer_groups)
        or (("Preceptores" in viewer_groups) and _preceptor_can_access_alumno(request.user, alumno))
    )

    if not (is_padre or is_prof_or_super or is_alumno_mismo or is_preceptor_ok):
        return HttpResponse("No tenés permiso para ver este perfil.", status=403)

    # ✅ NUEVO: contamos ausentes como 1 y "tarde" como 0.5
    asistencias_base_qs = scope_queryset_to_school(Asistencia.objects.filter(alumno=alumno), active_school)
    asistencias_irregulares = asistencias_base_qs.filter(
        Q(presente=False) | Q(tarde=True)
    ).order_by('-fecha')

    resumen_asist = asistencias_base_qs.aggregate(
        ausentes=Count("id", filter=Q(presente=False)),
        tardes=Count("id", filter=Q(presente=True, tarde=True)),
    )
    ausentes_cnt = int(resumen_asist.get("ausentes") or 0)
    tarde_cnt = int(resumen_asist.get("tardes") or 0)
    faltas_equivalentes = ausentes_cnt + (tarde_cnt * 0.5)

    return render(request, 'calificaciones/perfil_alumno.html', {
        'alumno': alumno,
        'asistencias_irregulares': asistencias_irregulares,
        'faltas_equivalentes': faltas_equivalentes,
    })
