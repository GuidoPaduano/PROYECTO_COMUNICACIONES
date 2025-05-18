from django.db import models
from django.contrib.auth.models import User

class Alumno(models.Model):
    CURSOS = [
        ("1A", "1°A"), ("1B", "1°B"),
        ("2A", "2°A"), ("2B", "2°B"),
        ("3A", "3°A"), ("3B", "3°B"),
        ("4ECO", "4° Economía"), ("4NAT", "4° Naturales"),
        ("5ECO", "5° Economía"), ("5NAT", "5° Naturales"),
        ("6ECO", "6° Economía"), ("6NAT", "6° Naturales"),
    ]

    nombre = models.CharField(max_length=100)
    id_alumno = models.CharField(max_length=10, unique=True)
    curso = models.CharField(max_length=10, choices=CURSOS)
    padre = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='hijos')

    def __str__(self):
        return self.nombre

class Nota(models.Model):
    CALIFICACION_CHOICES = [(str(i), str(i)) for i in range(1, 11)] + [
        ("TEA", "TEA"), ("TEP", "TEP"), ("TED", "TED")
    ]

    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE)
    materia = models.CharField(max_length=50)
    tipo = models.CharField(max_length=50)
    calificacion = models.CharField(max_length=3, choices=CALIFICACION_CHOICES)
    fecha = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"{self.alumno.nombre} - {self.materia} ({self.tipo}): {self.calificacion}"

class Mensaje(models.Model):
    emisor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mensajes_enviados')
    receptor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mensajes_recibidos')
    asunto = models.CharField(max_length=100)
    contenido = models.TextField()
    fecha_envio = models.DateTimeField(auto_now_add=True)
    curso_asociado = models.CharField(max_length=10, blank=True, null=True)

    def __str__(self):
        return f"Mensaje de {self.emisor} a {self.receptor}: {self.asunto}"

class Evento(models.Model):
    TIPOS_EVENTO = [
        ('evaluacion', 'Evaluación'),
        ('entrega', 'Entrega de TP'),
        ('otro', 'Otro'),
    ]

    titulo = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    fecha = models.DateField()
    curso = models.CharField(max_length=10, choices=Alumno.CURSOS)
    creado_por = models.ForeignKey(User, on_delete=models.CASCADE)
    tipo_evento = models.CharField(max_length=50, choices=TIPOS_EVENTO)

    def __str__(self):
        return f"{self.titulo} ({self.fecha})"
