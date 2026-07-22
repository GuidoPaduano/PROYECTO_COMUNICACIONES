from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from ._school import School
from ._alumno import Alumno
from ._integrity import ensure_school_for_save
from ._validators import validate_calificacion_ext


TIPOS_ASISTENCIA = (
    ("clases", "Clases"),
    ("informatica", "Informática"),
    ("catequesis", "Catequesis"),
)


class Nota(models.Model):
    MATERIAS = [
        ("Lengua", "Lengua"),
        ("Matemática", "Matemática"),
        ("Ciencias", "Ciencias"),
        ("Historia", "Historia"),
        ("Geografía", "Geografía"),
        ("Inglés", "Inglés"),
        ("Educación Física", "Educación Física"),
        ("Música", "Música"),
        ("Plástica", "Plástica"),
        ("Catequesis", "Catequesis"),
        ("Informática", "Informática"),
    ]
    TIPOS = [
        ("Examen", "Examen"),
        ("Trabajo Práctico", "Trabajo Práctico"),
        ("Participación", "Participación"),
        ("Tarea", "Tarea"),
        ("Nota Final", "Nota Final"),
    ]
    RESULTADO_CHOICES = [
        ("TEA", "Aprobado"),
        ("TEP", "Desaprobado"),
        ("TED", "Aplazado"),
    ]

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="notas")
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name="notas")
    materia = models.CharField(max_length=50, choices=MATERIAS)
    tipo = models.CharField(max_length=50, choices=TIPOS)
    calificacion = models.CharField(max_length=15, validators=[validate_calificacion_ext])
    resultado = models.CharField(max_length=3, choices=RESULTADO_CHOICES, null=True, blank=True, db_index=True)
    nota_numerica = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
    )
    cuatrimestre = models.IntegerField(choices=[(1, "1"), (2, "2")])
    fecha = models.DateField(default=timezone.now)
    observaciones = models.TextField(blank=True, null=True)
    es_final = models.BooleanField(default=False, db_index=True)
    anio_lectivo = models.IntegerField(null=True, blank=True, db_index=True)
    version = models.PositiveIntegerField(default=1)
    firmada = models.BooleanField(default=False, db_index=True)
    firmada_en = models.DateTimeField(null=True, blank=True)
    firmada_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="notas_firmadas",
    )

    class Meta:
        ordering = ["-fecha", "-id"]
        indexes = [models.Index(fields=["alumno", "materia", "fecha"])]
        constraints = [
            models.UniqueConstraint(
                condition=models.Q(es_final=True, anio_lectivo__isnull=False),
                fields=["alumno", "materia", "cuatrimestre", "anio_lectivo"],
                name="unique_nota_final_alumno_materia_cuatrimestre_anio",
            ),
        ]

    def __str__(self):
        return f"{self.alumno} - {self.materia}: {self.calificacion}"

    def save(self, *args, **kwargs):
        ensure_school_for_save(self, kwargs, related_fields=("alumno",))
        return super().save(*args, **kwargs)


class Asistencia(models.Model):
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="asistencias")
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name="asistencias")
    fecha = models.DateField(default=timezone.localdate, db_index=True)
    tipo_asistencia = models.CharField(max_length=20, choices=TIPOS_ASISTENCIA, default="clases", db_index=True)
    presente = models.BooleanField(default=True)
    tarde = models.BooleanField(default=False, db_index=True)
    justificada = models.BooleanField(default=False, db_index=True)
    observacion = models.CharField(max_length=255, blank=True, null=True)
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    firmada = models.BooleanField(default=False, db_index=True)
    firmada_en = models.DateTimeField(null=True, blank=True)
    firmada_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="asistencias_firmadas",
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-fecha", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["alumno", "fecha", "tipo_asistencia"],
                name="unique_asistencia_alumno_fecha_tipo",
            ),
            models.CheckConstraint(
                check=(models.Q(tarde=False) | models.Q(presente=True)),
                name="asistencia_tarde_requiere_presente",
            ),
            models.CheckConstraint(
                check=(models.Q(justificada=False) | models.Q(presente=False) | models.Q(tarde=True)),
                name="asistencia_justificada_requiere_ausente_o_tarde",
            ),
        ]
        indexes = [
            models.Index(fields=["alumno", "fecha", "tipo_asistencia"]),
            models.Index(fields=["alumno", "tipo_asistencia", "presente"]),
        ]

    def __str__(self):
        estado = "Ausente" if (not self.presente) else ("Tarde" if getattr(self, "tarde", False) else "Presente")
        return f"{self.alumno} - {self.fecha} - {self.tipo_asistencia} - {estado}"

    def save(self, *args, **kwargs):
        ensure_school_for_save(self, kwargs, related_fields=("alumno",))
        return super().save(*args, **kwargs)
