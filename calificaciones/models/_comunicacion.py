from django.contrib.auth.models import User
from django.db import models

from ._school import School, SchoolCourse
from ._alumno import Alumno
from ._integrity import ensure_school_for_save, ensure_school_course_for_save


class Mensaje(models.Model):
    REMITENTE_TIPOS = [
        ('Profesor', 'Profesor'),
        ('Preceptor', 'Preceptor'),
        ('Directivo', 'Directivo'),
    ]

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="mensajes")
    school_course = models.ForeignKey(SchoolCourse, on_delete=models.PROTECT, related_name="mensajes", null=True, blank=True)
    remitente = models.ForeignKey(User, on_delete=models.CASCADE, related_name="mensajes_enviados")
    destinatario = models.ForeignKey(User, on_delete=models.CASCADE, related_name="mensajes_recibidos")
    curso = models.CharField(max_length=20, blank=True, null=True, db_index=True)
    alumno = models.ForeignKey(Alumno, on_delete=models.SET_NULL, null=True, blank=True, related_name="mensajes")
    tipo_remitente = models.CharField(max_length=20, choices=REMITENTE_TIPOS, default="Profesor")
    asunto = models.CharField(max_length=255)
    contenido = models.TextField()
    fecha_envio = models.DateTimeField(auto_now_add=True)
    leido = models.BooleanField(default=False)
    leido_en = models.DateTimeField(null=True, blank=True, db_index=True)
    client_request_id = models.UUIDField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-fecha_envio", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["remitente", "client_request_id"],
                name="unique_mensaje_sender_request",
            ),
        ]
        indexes = [
            models.Index(fields=["destinatario", "leido", "fecha_envio"]),
            models.Index(fields=["destinatario", "fecha_envio"]),
            models.Index(fields=["remitente", "fecha_envio"]),
        ]

    def __str__(self):
        return f"{self.asunto} ({self.remitente} -> {self.destinatario})"

    def save(self, *args, **kwargs):
        ensure_school_course_for_save(self, kwargs)
        return super().save(*args, **kwargs)



class Notificacion(models.Model):
    TIPO_CHOICES = [
        ("nota", "Nota"),
        ("sancion", "Sanción"),
        ("inasistencia", "Inasistencia"),
        ("mensaje", "Mensaje"),
        ("evento", "Evento"),
        ("otro", "Otro"),
    ]

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="notificaciones")
    destinatario = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notificaciones", db_index=True)
    tipo = models.CharField(max_length=30, choices=TIPO_CHOICES, db_index=True)
    titulo = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    url = models.CharField(max_length=500, blank=True, null=True)
    creada_en = models.DateTimeField(auto_now_add=True, db_index=True)
    leida = models.BooleanField(default=False, db_index=True)
    meta = models.JSONField(blank=True, null=True)

    class Meta:
        ordering = ["-creada_en"]
        indexes = [
            models.Index(fields=["destinatario", "leida", "creada_en"]),
            models.Index(fields=["destinatario", "creada_en"]),
        ]

    def __str__(self):
        return f"{self.tipo}: {self.titulo}"

    def save(self, *args, **kwargs):
        ensure_school_for_save(self, kwargs)
        return super().save(*args, **kwargs)
