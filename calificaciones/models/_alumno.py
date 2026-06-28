from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models

from ._school import School, SchoolCourse
from ._integrity import ensure_school_course_for_save


class Alumno(models.Model):
    CURSOS = [
        ('1A', '1A'), ('1B', '1B'),
        ('2A', '2A'), ('2B', '2B'),
        ('3A', '3A'), ('3B', '3B'),
        ('4ECO', '4ECO'), ('4NAT', '4NAT'),
        ('5ECO', '5ECO'), ('5NAT', '5NAT'),
        ('6ECO', '6ECO'), ('6NAT', '6NAT'),
    ]

    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100, default="", blank=True)
    id_alumno = models.CharField(max_length=20, db_index=True)
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="alumnos")
    school_course = models.ForeignKey(SchoolCourse, on_delete=models.PROTECT, related_name="alumnos")
    curso = models.CharField(max_length=20, choices=CURSOS, db_index=True)
    padre = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="alumnos_como_padre")
    usuario = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="perfil_alumno")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["school", "id_alumno"],
                name="unique_alumno_school_legajo",
            ),
        ]

    def __str__(self):
        if self.apellido:
            return f"{self.apellido}, {self.nombre} ({self.curso})"
        return f"{self.nombre} ({self.curso})"

    def save(self, *args, **kwargs):
        ensure_school_course_for_save(self, kwargs)
        legajo = str(getattr(self, "id_alumno", "") or "").strip()
        school_id = getattr(self, "school_id", None)
        if legajo and school_id is not None:
            dupes = type(self).objects.filter(school_id=school_id, id_alumno__iexact=legajo)
            if self.pk:
                dupes = dupes.exclude(pk=self.pk)
            if dupes.exists():
                raise ValidationError({"id_alumno": "Ya existe un alumno con ese legajo en este colegio."})
        return super().save(*args, **kwargs)
