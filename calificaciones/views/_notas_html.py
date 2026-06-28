# calificaciones/views/_notas_html.py
# Vistas HTML para agregar notas y ver notas

from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt

from ..constants import MATERIAS
from ..forms import NotaForm
from ..models import Alumno, Nota
from ..schools import (
    get_request_school,
    scope_queryset_to_school,
)
from ..serializers import NotaCreateSerializer
from ._acceso import (
    _can_access_course_roster,
    _course_selection_querystring,
    _has_model_field,
    _has_role,
    _get_preview_role,
    _profesor_assignment_refs,
    _resolve_request_course_selection,
    _school_course_options_for_ui,
)
from ..course_access import course_ref_matches, filter_course_options_by_refs
from ..utils_cursos import get_school_course_choices
from ._cursos import _alumnos_por_curso_qs
from ._notificaciones import _notify_padre_por_nota, _notify_padres_por_notas_bulk


@login_required
def agregar_nota(request):
    if not (_has_role(request, "Profesores") or request.user.is_superuser):
        return HttpResponse("No tenés permiso.", status=403)

    active_school = get_request_school(request)
    cursos = get_school_course_choices(school=active_school)
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
            cursos = filter_course_options_by_refs(cursos, assigned_refs)
            if (curso_seleccionado_id or curso_seleccionado) and not course_ref_matches(
                assigned_refs,
                school_course_id=curso_seleccionado_id,
                course_code=curso_seleccionado,
            ):
                return HttpResponse("No tenés permiso para ese curso.", status=403)

    if request.method == "POST":
        alumnos_list = request.POST.getlist("alumno[]")

        if alumnos_list:
            materias_list = request.POST.getlist("materia[]")
            tipos_list = request.POST.getlist("tipo[]")
            califs_list = request.POST.getlist("calificacion[]")
            resultados_list = request.POST.getlist("resultado[]")
            notas_numericas_list = request.POST.getlist("nota_numerica[]")
            cuatris_list = request.POST.getlist("cuatrimestre[]")
            fechas_list = request.POST.getlist("fecha[]")

            creadas = 0
            errores = 0
            notas_creadas = []

            for i, alum_id_raw in enumerate(alumnos_list):
                alum_id = (alum_id_raw or "").strip()
                materia = (materias_list[i] or "").strip() if i < len(materias_list) else ""
                tipo = (tipos_list[i] or "").strip() if i < len(tipos_list) else ""
                calif = (califs_list[i] or "").strip() if i < len(califs_list) else ""
                resultado = (resultados_list[i] or "").strip() if i < len(resultados_list) else ""
                nota_numerica = (notas_numericas_list[i] or "").strip() if i < len(notas_numericas_list) else ""
                cuatr = (cuatris_list[i] or "").strip() if i < len(cuatris_list) else ""
                fstr = (fechas_list[i] or "").strip() if i < len(fechas_list) else ""
                fparsed = parse_date(fstr) if fstr else date.today()

                if not (alum_id and materia and tipo and cuatr):
                    errores += 1
                    continue

                try:
                    alumno = scope_queryset_to_school(Alumno.objects.all(), active_school).get(id_alumno=alum_id)
                except Alumno.DoesNotExist:
                    errores += 1
                    continue

                payload = {
                    "alumno": alumno.id,
                    "materia": materia,
                    "tipo": tipo,
                    "calificacion": calif,
                    "resultado": resultado,
                    "nota_numerica": nota_numerica,
                    "cuatrimestre": cuatr,
                    "fecha": (fparsed or date.today()).isoformat(),
                }
                ser = NotaCreateSerializer(data=payload)
                if ser.is_valid():
                    nota = ser.save(school=active_school or getattr(alumno, "school", None))
                    notas_creadas.append(nota)
                    creadas += 1
                else:
                    errores += 1

            try:
                _notify_padres_por_notas_bulk(request.user, notas_creadas)
            except Exception:
                pass

            if creadas:
                messages.success(request, f"Se guardaron {creadas} nota(s).")
            if errores:
                messages.error(request, f"{errores} fila(s) no pudieron guardarse. Revisa los datos.")
            return redirect(
                f"{request.path}{_course_selection_querystring(school_course_id=curso_seleccionado_id, course_code=curso_seleccionado or '')}"
            )

        alumno_id = request.POST.get("alumno")
        materia = request.POST.get("materia")
        tipo = request.POST.get("tipo")
        calificacion = request.POST.get("calificacion")
        resultado = request.POST.get("resultado")
        nota_numerica = request.POST.get("nota_numerica")
        cuatrimestre = request.POST.get("cuatrimestre")
        fecha_nota = parse_date(request.POST.get("fecha") or "") or date.today()

        try:
            alumno = scope_queryset_to_school(Alumno.objects.all(), active_school).get(id_alumno=alumno_id)
            payload = {
                "alumno": alumno.id,
                "materia": materia or "",
                "tipo": tipo or "",
                "calificacion": calificacion or "",
                "resultado": resultado or "",
                "nota_numerica": nota_numerica or "",
                "cuatrimestre": cuatrimestre,
                "fecha": fecha_nota.isoformat(),
            }
            ser = NotaCreateSerializer(data=payload)
            if not ser.is_valid():
                raise ValidationError(str(ser.errors))
            nota = ser.save(school=active_school or getattr(alumno, "school", None))

            try:
                _notify_padre_por_nota(request.user, nota)
            except Exception:
                pass

            messages.success(request, "Nota guardada correctamente.")
        except Alumno.DoesNotExist:
            messages.error(request, "Alumno no encontrado.")
        except ValidationError as e:
            messages.error(request, f"Carga inválida: {e}")
        except Exception as e:
            messages.error(request, f"No se pudo guardar la nota: {e}")
        return redirect("index")

    alumnos = []
    if curso_seleccionado:
        alumnos = _alumnos_por_curso_qs(curso_seleccionado, school=active_school).order_by("nombre")
    nota_form = NotaForm()
    nota_form.fields["alumno"].queryset = alumnos or Alumno.objects.none()

    return render(
        request,
        "calificaciones/agregar_nota.html",
        {
            "cursos": cursos,
            "curso_seleccionado": curso_seleccionado,
            "curso_seleccionado_id": curso_seleccionado_id,
            "alumnos": alumnos,
            "materias": MATERIAS,
            "resultados_catalogo": Nota.RESULTADO_CHOICES,
            "form": nota_form,
        },
    )


@csrf_exempt
@login_required
def agregar_nota_masiva(request):
    if not (_has_role(request, "Profesores") or request.user.is_superuser):
        return HttpResponse("No tenés permiso.", status=403)

    active_school = get_request_school(request)

    if request.method != "POST":
        return JsonResponse({"detail": "Metodo no permitido"}, status=405)

    if _has_role(request, "Profesores") and not request.user.is_superuser:
        assigned_refs = _profesor_assignment_refs(request.user, school=active_school)
        selected_course = _resolve_request_course_selection(
            request,
            school=active_school,
            required=False,
        )
        if selected_course["error"]:
            return JsonResponse({"detail": selected_course["error"]}, status=400)
        if assigned_refs:
            if (selected_course["school_course_id"] or selected_course["course_code"]) and not course_ref_matches(
                assigned_refs,
                school_course_id=selected_course["school_course_id"],
                course_code=selected_course["course_code"],
            ):
                return JsonResponse({"detail": "No autorizado para ese curso."}, status=403)
    else:
        selected_course = _resolve_request_course_selection(
            request,
            school=active_school,
            required=False,
        )
        if selected_course["error"]:
            return JsonResponse({"detail": selected_course["error"]}, status=400)

    alumnos_ids = request.POST.getlist("alumno[]")
    materias = request.POST.getlist("materia[]")
    tipos = request.POST.getlist("tipo[]")
    califs = request.POST.getlist("calificacion[]")
    resultados = request.POST.getlist("resultado[]")
    notas_numericas = request.POST.getlist("nota_numerica[]")
    cuatris = request.POST.getlist("cuatrimestre[]")
    fechas = request.POST.getlist("fecha[]")

    if not alumnos_ids and request.POST.get("alumno"):
        alumnos_ids = [request.POST.get("alumno")]
        materias = [request.POST.get("materia")]
        tipos = [request.POST.get("tipo")]
        califs = [request.POST.get("calificacion")]
        resultados = [request.POST.get("resultado")]
        notas_numericas = [request.POST.get("nota_numerica")]
        cuatris = [request.POST.get("cuatrimestre")]
        fechas = [request.POST.get("fecha")] if request.POST.get("fecha") else []

    if len(alumnos_ids) == 0:
        return JsonResponse({"creadas": 0, "detail": "Sin filas validas"}, status=400)

    errores = 0
    notas_creadas = []

    for i, alum_id_raw in enumerate(alumnos_ids):
        alum_id = (alum_id_raw or "").strip()
        materia = (materias[i] or "").strip() if i < len(materias) else ""
        tipo = (tipos[i] or "").strip() if i < len(tipos) else ""
        calif = (califs[i] or "").strip() if i < len(califs) else ""
        resultado = (resultados[i] or "").strip() if i < len(resultados) else ""
        nota_numerica = (notas_numericas[i] or "").strip() if i < len(notas_numericas) else ""
        cuatr = (cuatris[i] or "").strip() if i < len(cuatris) else ""
        f = parse_date(fechas[i]) if i < len(fechas) and fechas[i] else date.today()

        if not (alum_id and materia and tipo and cuatr):
            errores += 1
            continue

        try:
            alumno = scope_queryset_to_school(Alumno.objects.all(), active_school).get(id_alumno=alum_id)
        except Alumno.DoesNotExist:
            errores += 1
            continue

        payload = {
            "alumno": alumno.id,
            "materia": materia,
            "tipo": tipo,
            "calificacion": calif,
            "resultado": resultado,
            "nota_numerica": nota_numerica,
            "cuatrimestre": cuatr,
            "fecha": (f or date.today()).isoformat(),
        }
        ser = NotaCreateSerializer(data=payload)
        if ser.is_valid():
            notas_creadas.append(ser.save(school=active_school or getattr(alumno, "school", None)))
        else:
            errores += 1

    creadas = len(notas_creadas)
    if notas_creadas:
        try:
            _notify_padres_por_notas_bulk(request.user, notas_creadas)
        except Exception:
            pass

    accept = (request.headers.get("Accept") or "").lower()
    selected_course = _resolve_request_course_selection(
        request,
        school=active_school,
        required=False,
    )
    if selected_course["error"]:
        return JsonResponse({"detail": selected_course["error"]}, status=400)
    curso_qs = selected_course["course_code"] or ""
    curso_qs_id = selected_course["school_course_id"]
    if "text/html" in accept:
        return redirect(f"/agregar_nota{_course_selection_querystring(school_course_id=curso_qs_id, course_code=curso_qs)}")

    return JsonResponse({"creadas": creadas, "errores": errores})


@login_required
def ver_notas(request):
    # Permitir ver esta pantalla si la vista previa es "Padres"
    if _has_role(request, 'Padres') or request.user.is_superuser:
        active_school = get_request_school(request)
        alumnos_qs = scope_queryset_to_school(
            Alumno.objects.select_related("school_course"),
            active_school,
        )
        alumnos = alumnos_qs.filter(padre=request.user)

        # Fallback para vista previa: tomar un padre real y sus hijos si no hay vínculos
        if not alumnos.exists() and _get_preview_role(request):
            a0 = alumnos_qs.filter(padre__isnull=False).order_by('padre_id').first()
            if a0 and a0.padre_id:
                alumnos = alumnos_qs.filter(padre_id=a0.padre_id)

        notas = scope_queryset_to_school(
            Nota.objects.filter(alumno__in=alumnos).select_related("alumno", "alumno__school_course"),
            active_school,
        ).order_by('cuatrimestre')
        return render(request, 'calificaciones/ver_notas.html', {'notas': notas})
    else:
        return HttpResponse("No tienes permiso para ver notas.", status=403)
