# calificaciones/models_preceptores.py
from django.contrib.auth import get_user_model
from django.db import models

from .models import Alumno, School, SchoolCourse, ensure_school_course_for_save

User = get_user_model()


class PreceptorCurso(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name="preceptor_asignaciones",
    )
    school_course = models.ForeignKey(
        SchoolCourse,
        on_delete=models.PROTECT,
        related_name="preceptor_asignaciones",
    )
    preceptor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="cursos_asignados",
    )
    curso = models.CharField(
        max_length=20,
        choices=Alumno.CURSOS,
        db_index=True,
    )
    asignado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("preceptor", "school", "curso")
        verbose_name = "Asignaci\u00f3n de curso a preceptor"
        verbose_name_plural = "Asignaciones de cursos a preceptores"
        indexes = [
            models.Index(fields=["curso"]),
            models.Index(fields=["preceptor"]),
        ]

    def __str__(self):
        return f"{self.preceptor} -> {self.curso}"

    def save(self, *args, **kwargs):
        ensure_school_course_for_save(self, kwargs)
        return super().save(*args, **kwargs)


class ProfesorCurso(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name="profesor_asignaciones",
    )
    school_course = models.ForeignKey(
        SchoolCourse,
        on_delete=models.PROTECT,
        related_name="profesor_asignaciones",
    )
    profesor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="cursos_asignados_profesor",
    )
    curso = models.CharField(
        max_length=20,
        choices=Alumno.CURSOS,
        db_index=True,
    )
    asignado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("profesor", "school", "curso")
        verbose_name = "Asignaci\u00f3n de curso a profesor"
        verbose_name_plural = "Asignaciones de cursos a profesores"
        indexes = [
            models.Index(fields=["curso"]),
            models.Index(fields=["profesor"]),
        ]

    def __str__(self):
        return f"{self.profesor} -> {self.curso}"

    def save(self, *args, **kwargs):
        ensure_school_course_for_save(self, kwargs)
        return super().save(*args, **kwargs)


class SchoolAdmin(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name="school_admin_assignments",
    )
    admin = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="school_admin_assignments",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("school", "admin")
        verbose_name = "Administrador de colegio"
        verbose_name_plural = "Administradores de colegio"
        indexes = [
            models.Index(fields=["school", "admin"]),
            models.Index(fields=["admin"]),
        ]

    def __str__(self):
        return f"{self.school} -> {self.admin}"
