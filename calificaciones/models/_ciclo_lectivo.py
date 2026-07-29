from django.db import models

from ._school import School, SchoolCourse
from ._alumno import Alumno


class CicloLectivo(models.Model):
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="ciclos_lectivos")
    anio = models.PositiveIntegerField()
    nombre = models.CharField(max_length=40, blank=True)
    activo = models.BooleanField(default=False, db_index=True)
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_fin = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-anio"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "anio"],
                name="unique_ciclo_lectivo_school_anio",
            ),
        ]

    def __str__(self):
        return self.nombre or str(self.anio)


class Matricula(models.Model):
    ESTADO_CHOICES = [
        ("activa", "Activa"),
        ("promovida", "Promovida"),
        ("transferida", "Transferida"),
        ("egresada", "Egresada"),
        ("baja", "Baja"),
    ]

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="matriculas")
    ciclo_lectivo = models.ForeignKey(CicloLectivo, on_delete=models.PROTECT, related_name="matriculas")
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name="matriculas")
    school_course = models.ForeignKey(SchoolCourse, on_delete=models.PROTECT, related_name="matriculas")
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="activa", db_index=True)
    fecha_desde = models.DateField(null=True, blank=True)
    fecha_hasta = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-ciclo_lectivo__anio"]
        constraints = [
            models.UniqueConstraint(
                fields=["ciclo_lectivo", "alumno"],
                name="unique_matricula_ciclo_alumno",
            ),
        ]

    def __str__(self):
        return f"{self.alumno} — {self.ciclo_lectivo} ({self.school_course})"
