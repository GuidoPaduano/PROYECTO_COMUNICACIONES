from django.conf import settings
from django.db import models


class PpiDocument(models.Model):
    alumno = models.ForeignKey('Alumno', on_delete=models.CASCADE, related_name='ppi_documents')
    titulo = models.CharField(max_length=200)
    nombre_archivo = models.CharField(max_length=255)
    # Served only through an authenticated endpoint, never through public media URLs.
    contenido = models.BinaryField(editable=False)
    tamano = models.PositiveIntegerField()
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creado_en', '-id']
