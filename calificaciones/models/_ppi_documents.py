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
    requiere_firma = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=1)
    version_anterior = models.OneToOneField('self', null=True, blank=True, on_delete=models.PROTECT, related_name='version_siguiente')
    sha256 = models.CharField(max_length=64, blank=True)


    class Meta:
        ordering = ['-creado_en', '-id']


class PpiDocumentReceipt(models.Model):
    documento = models.ForeignKey(PpiDocument, on_delete=models.CASCADE, related_name='receipts')
    docente = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    nombre_docente = models.CharField(max_length=255)
    consultado_en = models.DateTimeField(null=True, blank=True)
    firmado_en = models.DateTimeField(null=True, blank=True)
    declaracion = models.CharField(max_length=255, blank=True)
    ultimo_recordatorio_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['documento', 'docente'], name='unique_ppi_document_teacher')]
        ordering = ['nombre_docente', 'id']
