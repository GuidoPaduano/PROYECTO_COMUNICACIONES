from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from .models import Alumno, Nota, Mensaje, Evento, Asistencia
from reportlab.pdfgen import canvas
from django.contrib.auth.models import User
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .serializers import EventoSerializer
from django import forms
from django.contrib import messages
from datetime import date

MATERIAS = [
    'Matemática', 'Lengua', 'Historia', 'Geografía',
    'Ciencias Naturales', 'Educación Física',
    'Tecnología', 'Inglés'
]

class EventoForm(forms.ModelForm):
    class Meta:
        model = Evento
        fields = ['titulo', 'descripcion', 'fecha', 'curso', 'tipo_evento']
        widgets = {
            'fecha': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }

@login_required
def index(request):
    if request.user.groups.filter(name='Padres').exists():
        return render(request, 'calificaciones/index.html')
    elif request.user.groups.filter(name='Profesores').exists() or request.user.is_superuser:
        return render(request, 'calificaciones/index.html')
    else:
        return HttpResponse("No tienes permiso.", status=403)

@login_required
def agregar_nota(request):
    if not (request.user.groups.filter(name='Profesores').exists() or request.user.is_superuser):
        return HttpResponse("No tenés permiso.", status=403)

    curso_seleccionado = request.GET.get('curso')
    alumnos = Alumno.objects.filter(curso=curso_seleccionado) if curso_seleccionado else []

    if request.method == 'POST':
        alumno_id = request.POST['alumno']
        materia = request.POST['materia']
        tipo = request.POST['tipo']
        calificacion = request.POST['calificacion']
        cuatrimestre = request.POST['cuatrimestre']
        alumno = Alumno.objects.get(id_alumno=alumno_id)
        Nota.objects.create(
            alumno=alumno,
            materia=materia,
            tipo=tipo,
            calificacion=calificacion,
            cuatrimestre=cuatrimestre
        )
        messages.success(request, "✅ Nota guardada correctamente.")
        return redirect('index')

    cursos = Alumno.CURSOS
    return render(request, 'calificaciones/agregar_nota.html', {
        'cursos': cursos,
        'curso_seleccionado': curso_seleccionado,
        'alumnos': alumnos,
        'materias': MATERIAS
    })

@login_required
def ver_notas(request):
    if request.user.groups.filter(name='Padres').exists():
        alumnos = Alumno.objects.filter(padre=request.user)
        notas = Nota.objects.filter(alumno__in=alumnos).order_by('alumno', 'cuatrimestre')
        return render(request, 'calificaciones/ver_notas.html', {'notas': notas})
    else:
        return HttpResponse("No tienes permiso para ver notas.", status=403)

@login_required
def enviar_mensaje(request):
    if not (request.user.groups.filter(name='Profesores').exists() or request.user.is_superuser):
        return HttpResponse("No tenés permiso.", status=403)

    cursos_disponibles = Alumno.CURSOS
    curso_seleccionado = request.GET.get('curso')
    alumnos = Alumno.objects.filter(curso=curso_seleccionado) if curso_seleccionado else []

    if request.method == 'POST':
        alumno_id = request.POST['alumno']
        asunto = request.POST['asunto']
        contenido = request.POST['contenido']
        alumno = Alumno.objects.get(id=alumno_id)
        receptor = alumno.padre
        if receptor:
            Mensaje.objects.create(emisor=request.user, receptor=receptor, asunto=asunto, contenido=contenido)
            return redirect('index')
        else:
            return HttpResponse("Este alumno no tiene padre asignado.", status=400)

    return render(request, 'calificaciones/enviar_mensaje.html', {
        'cursos': cursos_disponibles,
        'curso_seleccionado': curso_seleccionado,
        'alumnos': alumnos
    })

@login_required
def enviar_comunicado(request):
    if not (request.user.groups.filter(name='Profesores').exists() or request.user.is_superuser):
        return HttpResponse("No tenés permiso.", status=403)

    cursos = Alumno.CURSOS

    if request.method == 'POST':
        curso = request.POST['curso']
        asunto = request.POST['asunto']
        contenido = request.POST['contenido']
        alumnos = Alumno.objects.filter(curso=curso, padre__isnull=False)
        for alumno in alumnos:
            Mensaje.objects.create(
                emisor=request.user,
                receptor=alumno.padre,
                asunto=asunto,
                contenido=contenido,
                curso_asociado=curso
            )
        return redirect('index')

    return render(request, 'calificaciones/enviar_comunicado.html', {'cursos': cursos})

@login_required
def ver_mensajes(request):
    if request.user.groups.filter(name='Padres').exists():
        alumnos = Alumno.objects.filter(padre=request.user)
        mensajes = Mensaje.objects.filter(alumno__in=alumnos).order_by('-fecha')
        return render(request, 'calificaciones/ver_mensajes.html', {'mensajes': mensajes})
    else:
        return HttpResponse("No tienes permiso para ver mensajes.", status=403)

@login_required
def generar_boletin_pdf(request, alumno_id):
    alumno = get_object_or_404(Alumno, id_alumno=alumno_id)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="boletin_{alumno.nombre}.pdf"'
    p = canvas.Canvas(response)
    p.drawString(100, 800, f"Boletín de {alumno.nombre}")
    y = 750
    notas = Nota.objects.filter(alumno=alumno).order_by('cuatrimestre')
    for nota in notas:
        p.drawString(100, y, f"{nota.materia} - Cuatrimestre {nota.cuatrimestre}: {nota.calificacion}")
        y -= 20
    p.showPage()
    p.save()
    return response

@login_required
def historial_notas_profesor(request, alumno_id):
    if not (request.user.groups.filter(name='Profesores').exists() or request.user.is_superuser):
        return HttpResponse("No tenés permiso para ver esto.", status=403)

    alumno = get_object_or_404(Alumno, id_alumno=alumno_id)
    materias = set(Nota.objects.filter(alumno=alumno).values_list('materia', flat=True))
    materia_seleccionada = request.GET.get('materia')
    notas = []

    if materia_seleccionada:
        notas = Nota.objects.filter(alumno=alumno, materia=materia_seleccionada).order_by('cuatrimestre')

    return render(request, 'calificaciones/historial_notas.html', {
        'alumno': alumno,
        'materias': materias,
        'materia_seleccionada': materia_seleccionada,
        'notas': notas
    })

@login_required
def historial_notas_padre(request):
    if not request.user.groups.filter(name='Padres').exists():
        return HttpResponse("No tenés permiso para ver esto.", status=403)

    alumnos = Alumno.objects.filter(padre=request.user)
    alumno = alumnos.first()

    materias = set(Nota.objects.filter(alumno=alumno).values_list('materia', flat=True))
    materia_seleccionada = request.GET.get('materia')
    notas = []

    if materia_seleccionada:
        notas = Nota.objects.filter(alumno=alumno, materia=materia_seleccionada).order_by('cuatrimestre')

    return render(request, 'calificaciones/historial_notas.html', {
        'alumno': alumno,
        'materias': materias,
        'materia_seleccionada': materia_seleccionada,
        'notas': notas
    })

class EventoViewSet(viewsets.ModelViewSet):
    queryset = Evento.objects.all()
    serializer_class = EventoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        if user.is_superuser or user.groups.filter(name='Profesores').exists():
            return Evento.objects.all()

        try:
            alumno = Alumno.objects.get(padre=user)
            return Evento.objects.filter(curso=alumno.curso)
        except Alumno.DoesNotExist:
            return Evento.objects.none()

@login_required
def calendario_view(request):
    form = EventoForm()
    return render(request, 'calificaciones/calendario.html', {'form': form})

@login_required
def crear_evento(request):
    if not (request.user.groups.filter(name='Profesores').exists() or request.user.is_superuser):
        return HttpResponse("No tenés permiso para crear eventos.", status=403)

    if request.method == 'POST':
        form = EventoForm(request.POST)
        if form.is_valid():
            evento = form.save(commit=False)
            evento.creado_por = request.user
            evento.save()
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'success': False, 'errors': form.errors}, status=400)

    return JsonResponse({'error': 'Método no permitido'}, status=405)

@login_required
def editar_evento(request, evento_id):
    evento = get_object_or_404(Evento, id=evento_id)

    if not (request.user == evento.creado_por or request.user.is_superuser):
        return HttpResponse("No tenés permiso para editar este evento.", status=403)

    if request.method == 'POST':
        form = EventoForm(request.POST, instance=evento)
        if form.is_valid():
            form.save()
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'success': False, 'errors': form.errors}, status=400)
    else:
        form = EventoForm(instance=evento)
        return render(request, 'calificaciones/parcial_editar_evento.html', {'form': form, 'evento': evento})

@login_required
def eliminar_evento(request, evento_id):
    evento = get_object_or_404(Evento, id=evento_id)

    if not (request.user == evento.creado_por or request.user.is_superuser):
        return HttpResponse("No tenés permiso para eliminar este evento.", status=403)

    if request.method == 'POST':
        evento.delete()
        return redirect('calendario')

    return render(request, 'calificaciones/confirmar_eliminar_evento.html', {
        'evento': evento
    })

@login_required
def pasar_asistencia(request):
    usuario = request.user
    alumnos = []
    curso_id = None
    curso_nombre = None

    if usuario.is_superuser:
        cursos = [{'id': c[0], 'nombre': c[1]} for c in Alumno.CURSOS]
        curso_id = request.GET.get('curso')
        if curso_id:
            curso_nombre = dict(Alumno.CURSOS).get(curso_id)
    else:
        curso_id = obtener_curso_del_preceptor(usuario)
        if not curso_id:
            return render(request, 'calificaciones/error.html', {'mensaje': 'No tenés un curso asignado como preceptor.'})
        curso_nombre = dict(Alumno.CURSOS).get(curso_id)
        cursos = [{'id': curso_id, 'nombre': curso_nombre}]

    if curso_id:
        alumnos = Alumno.objects.filter(curso=curso_id).order_by('apellido', 'nombre')

    if request.method == 'POST':
        fecha_actual = date.today()
        asistencia_objs = []
        for alumno in alumnos:
            presente = request.POST.get(f'asistencia_{alumno.id}') == 'on'
            asistencia_objs.append(Asistencia(
                alumno=alumno,
                fecha=fecha_actual,
                presente=presente
            ))

        Asistencia.objects.filter(alumno__in=alumnos, fecha=fecha_actual).delete()
        Asistencia.objects.bulk_create(asistencia_objs)

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True})
        return redirect('index')

    return render(request, 'calificaciones/pasar_asistencia.html', {
        'alumnos': alumnos,
        'curso_id': curso_id,
        'curso_nombre': curso_nombre,
        'cursos': cursos
    })

@login_required
def perfil_alumno(request, alumno_id):
    alumno = get_object_or_404(Alumno, id_alumno=alumno_id)

    if request.user != alumno.padre and not request.user.is_superuser and not request.user.groups.filter(name='Profesores').exists():
        return HttpResponse("No tenés permiso para ver este perfil.", status=403)

    inasistencias = Asistencia.objects.filter(alumno=alumno, presente=False).order_by('-fecha')

    return render(request, 'calificaciones/perfil_alumno.html', {
        'alumno': alumno,
        'inasistencias': inasistencias,
    })

def obtener_curso_del_preceptor(usuario):
    cursos_por_usuario = {
        'preceptor1': '1A',
        'preceptor2': '3B',
        'preceptor3': '5NAT',
    }
    return cursos_por_usuario.get(usuario.username, None)

@login_required
def mi_perfil(request):
    user = request.user
    return render(request, 'calificaciones/mi_perfil.html', {'user': user})

@login_required
def vista_alumno(request):
    if not request.user.groups.filter(name='Alumnos').exists():
        return HttpResponse("No tenés permiso para ver esta página.", status=403)

    try:
        alumno = Alumno.objects.get(usuario=request.user)
    except Alumno.DoesNotExist:
        return HttpResponse("No se encontró un alumno vinculado a este usuario.", status=404)

    notas = Nota.objects.filter(alumno=alumno).order_by('cuatrimestre', 'materia')
    asistencias = Asistencia.objects.filter(alumno=alumno).order_by('-fecha')

    return render(request, 'calificaciones/vista_alumno.html', {
        'alumno': alumno,
        'notas': notas,
        'asistencias': asistencias
    })

