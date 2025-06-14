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
    apellido = models.CharField(max_length=100, default="")  # Nuevo campo
    id_alumno = models.CharField(max_length=10, unique=True)
    curso = models.CharField(max_length=10, choices=CURSOS)
    padre = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='hijos')
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True, related_name='perfil_alumno')  # Nuevo campo

    def __str__(self):
        return f"{self.apellido}, {self.nombre}"

class Nota(models.Model):
    CALIFICACION_CHOICES = [(str(i), str(i)) for i in range(1, 11)] + [
        ("TEA", "TEA"), ("TEP", "TEP"), ("TED", "TED")
    ]

    CUATRIMESTRE_CHOICES = [
        (1, "1er cuatrimestre"),
        (2, "2do cuatrimestre")
    ]

    TIPO_NOTA_CHOICES = [
        ("evaluacion", "Evaluación"),
        ("tp", "Trabajo Práctico"),
        ("oral", "Oral"),
        ("recuperatorio", "Recuperatorio"),
    ]

    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE)
    materia = models.CharField(max_length=50)
    tipo = models.CharField(max_length=20, choices=TIPO_NOTA_CHOICES)
    calificacion = models.CharField(max_length=3, choices=CALIFICACION_CHOICES)
    cuatrimestre = models.IntegerField(choices=CUATRIMESTRE_CHOICES, default=1)
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

class Asistencia(models.Model):
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE)
    fecha = models.DateField(auto_now_add=True)
    presente = models.BooleanField(default=True)
    observacion = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('alumno', 'fecha')

    def __str__(self):
        estado = "Presente" if self.presente else "Ausente"
        return f"{self.alumno.nombre} - {estado} - {self.fecha}"
