# calificaciones/models_preceptores.py
from django.db import models
from django.contrib.auth import get_user_model

# Importamos Alumno para reutilizar el catálogo de cursos (choices)
from .models import Alumno

User = get_user_model()

class PreceptorCurso(models.Model):
    preceptor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="cursos_asignados"
    )
    curso = models.CharField(
        max_length=20,
        choices=Alumno.CURSOS,
        db_index=True
    )
    asignado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("preceptor", "curso")
        verbose_name = "Asignación de curso a preceptor"
        verbose_name_plural = "Asignaciones de cursos a preceptores"
        indexes = [
            models.Index(fields=["curso"]),
            models.Index(fields=["preceptor"]),
        ]

    def __str__(self):
        return f"{self.preceptor} → {self.curso}"
