from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from ._school import School, SchoolCourse
from ._alumno import Alumno
from ._academico import Nota, Asistencia
from ._integrity import ensure_school_for_save, ensure_school_course_for_save


TIPOS_EVENTO = [
    ('Evaluación', 'Evaluación'),
    ('Entrega', 'Entrega'),
    ('Acto', 'Acto'),
    ('Reunión', 'Reunión'),
    ('Otro', 'Otro'),
]


class Sancion(models.Model):
    TIPOS = [
        ('Amonestación', 'Amonestación'),
        ('Llamado de atención', 'Llamado de atención'),
        ('Suspensión', 'Suspensión'),
    ]

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="sanciones")
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name="sanciones")
    tipo = models.CharField(max_length=50, choices=TIPOS, default="Amonestación")
    motivo = models.TextField()
    detalle = models.TextField(blank=True, null=True)
    fecha = models.DateField(default=timezone.now)
    docente = models.CharField(max_length=100, blank=True, null=True)
    firmada = models.BooleanField(default=False, db_index=True)
    firmada_en = models.DateTimeField(null=True, blank=True)
    firmada_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="sanciones_firmadas",
    )

    class Meta:
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"{self.alumno} - {self.tipo} ({self.fecha})"

    def save(self, *args, **kwargs):
        ensure_school_for_save(self, kwargs, related_fields=("alumno",))
        return super().save(*args, **kwargs)


class Evento(models.Model):
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="eventos")
    school_course = models.ForeignKey(SchoolCourse, on_delete=models.PROTECT, related_name="eventos")
    titulo = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    curso = models.CharField(max_length=20, choices=Alumno.CURSOS, db_index=True)
    fecha = models.DateField()
    tipo_evento = models.CharField(max_length=50, choices=TIPOS_EVENTO, default='Otro')
    creado_por = models.ForeignKey(
        User, blank=True, null=True, on_delete=models.SET_NULL, related_name="eventos_creados",
    )

    class Meta:
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"{self.titulo} ({self.fecha})"

    def save(self, *args, **kwargs):
        ensure_school_course_for_save(self, kwargs)
        return super().save(*args, **kwargs)


class AlertaAcademica(models.Model):
    ESTADO_CHOICES = [
        ("activa", "Activa"),
        ("cerrada", "Cerrada"),
    ]

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="alertas_academicas")
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name="alertas_academicas", db_index=True)
    materia = models.CharField(max_length=50, db_index=True)
    cuatrimestre = models.IntegerField(null=True, blank=True, db_index=True)
    severidad = models.IntegerField(db_index=True)
    riesgo_ponderado = models.DecimalField(max_digits=4, decimal_places=3, default=0)
    triggers = models.JSONField(default=dict, blank=True)
    ventana_desde = models.DateField(null=True, blank=True)
    ventana_hasta = models.DateField(null=True, blank=True)
    fecha_evento = models.DateField(default=timezone.localdate, db_index=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="activa", db_index=True)
    nota_disparadora = models.ForeignKey(
        Nota, on_delete=models.SET_NULL, null=True, blank=True, related_name="alertas_disparadas",
    )
    creada_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="alertas_creadas",
    )
    creada_en = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-creada_en", "-id"]
        indexes = [
            models.Index(fields=["alumno", "materia", "creada_en"]),
            models.Index(fields=["alumno", "materia", "cuatrimestre"]),
        ]

    def __str__(self):
        return f"Alerta N{self.severidad} - {self.alumno} - {self.materia}"

    def save(self, *args, **kwargs):
        ensure_school_for_save(self, kwargs, related_fields=("alumno", "nota_disparadora"))
        return super().save(*args, **kwargs)


class AlertaInasistencia(models.Model):
    ESTADO_CHOICES = [
        ("activa", "Activa"),
        ("cerrada", "Cerrada"),
    ]
    MOTIVO_CHOICES = [
        ("AUSENCIAS_CONSECUTIVAS", "Ausencias consecutivas"),
        ("FALTAS_ACUMULADAS", "Faltas acumuladas"),
    ]

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="alertas_inasistencias")
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name="alertas_inasistencia", db_index=True)
    school_course = models.ForeignKey(SchoolCourse, on_delete=models.PROTECT, related_name="alertas_inasistencia")
    curso = models.CharField(max_length=20, db_index=True)
    tipo_asistencia = models.CharField(max_length=20, default="clases", db_index=True)
    motivo = models.CharField(max_length=40, choices=MOTIVO_CHOICES, db_index=True)
    severidad = models.IntegerField(default=1, db_index=True)
    valor_actual = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    umbral = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="activa", db_index=True)
    fecha_evento = models.DateField(default=timezone.localdate, db_index=True)
    detalle = models.JSONField(default=dict, blank=True)
    asistencia_disparadora = models.ForeignKey(
        Asistencia, on_delete=models.SET_NULL, null=True, blank=True, related_name="alertas_inasistencia_disparadas",
    )
    creada_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="alertas_inasistencia_creadas",
    )
    creada_en = models.DateTimeField(auto_now_add=True, db_index=True)
    cerrada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creada_en", "-id"]
        indexes = [
            models.Index(fields=["alumno", "motivo", "estado"]),
            models.Index(fields=["curso", "estado", "creada_en"]),
            models.Index(fields=["school_course", "estado", "creada_en"], name="calificacio_school__3caeb5_idx"),
        ]

    def __str__(self):
        return f"Inasistencia ({self.motivo}) - {self.alumno}"

    def save(self, *args, **kwargs):
        ensure_school_for_save(self, kwargs, related_fields=("alumno", "asistencia_disparadora"))
        ensure_school_course_for_save(self, kwargs)
        return super().save(*args, **kwargs)
