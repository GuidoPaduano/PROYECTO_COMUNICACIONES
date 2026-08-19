from django.contrib.auth.models import User
from django.db import models

from ._school import School, SchoolCourse


def _documento_upload_path(instance, filename):
    return f"documentos/school_{instance.school_id}/{filename}"


class Documento(models.Model):
    TIPO_CHOICES = [
        ("autorizacion", "Autorización"),
        ("normas", "Normas de convivencia"),
        ("circular", "Circular"),
        ("otro", "Otro"),
    ]

    DESTINATARIO_CHOICES = [
        ("todos", "Padres y alumnos"),
        ("padres", "Solo padres"),
        ("alumnos", "Solo alumnos"),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="documentos")
    school_course = models.ForeignKey(
        SchoolCourse, on_delete=models.SET_NULL, null=True, blank=True, related_name="documentos"
    )
    titulo = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, default="")
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="otro")
    destinatario = models.CharField(max_length=20, choices=DESTINATARIO_CHOICES, default="todos")
    archivo = models.FileField(upload_to=_documento_upload_path)
    subido_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="documentos_subidos")
    creado_en = models.DateTimeField(auto_now_add=True)
    requiere_firma = models.BooleanField(default=True)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self):
        return f"{self.titulo} ({self.school})"


class FirmaDocumento(models.Model):
    documento = models.ForeignKey(Documento, on_delete=models.CASCADE, related_name="firmas")
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name="firmas_documentos")
    fecha_firma = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        unique_together = [("documento", "usuario")]
        ordering = ["fecha_firma"]

    def __str__(self):
        return f"{self.usuario} firmó '{self.documento.titulo}'"
