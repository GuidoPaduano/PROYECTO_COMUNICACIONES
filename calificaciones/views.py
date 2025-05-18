from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from .models import Alumno, Nota, Mensaje, Evento
from reportlab.pdfgen import canvas
from django.contrib.auth.models import User
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .serializers import EventoSerializer
from django import forms

# Lista de materias predeterminadas
MATERIAS = [
    'Matemática', 'Lengua', 'Historia', 'Geografía',
    'Ciencias Naturales', 'Educación Física',
    'Tecnología', 'Inglés'
]

# FORMULARIO DE EVENTO (sin campo hora)
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
        alumnos = Alumno.objects.filter(padre=request.user)
    elif request.user.groups.filter(name='Profesores').exists() or request.user.is_superuser:
        alumnos = Alumno.objects.all()
    else:
        return HttpResponse("No tienes permiso.", status=403)
    return render(request, 'calificaciones/index.html', {'alumnos': alumnos})

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
        alumno = Alumno.objects.get(id=alumno_id)
        Nota.objects.create(
            alumno=alumno,
            materia=materia,
            tipo=tipo,
            calificacion=calificacion
        )
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
        notas = Nota.objects.filter(alumno__in=alumnos).order_by('alumno', 'trimestre')
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
    notas = Nota.objects.filter(alumno=alumno).order_by('trimestre')
    for nota in notas:
        p.drawString(100, y, f"{nota.materia} - Trimestre {nota.trimestre}: {nota.calificacion}")
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
        notas = Nota.objects.filter(alumno=alumno, materia=materia_seleccionada).order_by('trimestre')

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
        notas = Nota.objects.filter(alumno=alumno, materia=materia_seleccionada).order_by('trimestre')

    return render(request, 'calificaciones/historial_notas.html', {
        'alumno': alumno,
        'materias': materias,
        'materia_seleccionada': materia_seleccionada,
        'notas': notas
    })

# -------------------- CALENDARIO --------------------

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

#FORZAR REDEPLOY#

