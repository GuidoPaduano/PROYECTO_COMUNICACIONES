from django.contrib.auth.models import User
from django.db import models

from ._alumno import Alumno
from ._comunicacion import Mensaje
from ._school import School


class Reunion(models.Model):
    MODALIDADES = [("presencial", "Presencial"), ("virtual", "Virtual")]
    ESTADOS = [("pendiente", "Pendiente"), ("confirmada", "Confirmada"),
               ("cambio_solicitado", "Cambio solicitado"), ("cancelada", "Cancelada")]

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="reuniones")
    alumno = models.ForeignKey(Alumno, on_delete=models.PROTECT, related_name="reuniones")
    organizador = models.ForeignKey(User, on_delete=models.PROTECT, related_name="reuniones_organizadas")
    familiar = models.ForeignKey(User, on_delete=models.PROTECT, related_name="reuniones_familiares")
    mensaje_familia = models.OneToOneField(
        Mensaje, on_delete=models.SET_NULL, null=True, blank=True, related_name="reunion_invitacion"
    )
    inicio = models.DateTimeField(db_index=True)
    duracion_minutos = models.PositiveSmallIntegerField(default=30)
    modalidad = models.CharField(max_length=12, choices=MODALIDADES)
    lugar = models.CharField(max_length=255, blank=True)
    motivo = models.CharField(max_length=500)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente")
    respuesta_familiar_en = models.DateTimeField(null=True, blank=True)
    nota_familiar = models.CharField(max_length=500, blank=True)
    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["inicio", "id"]
        indexes = [models.Index(fields=["school", "inicio"])]


class InvitadoReunion(models.Model):
    reunion = models.ForeignKey(Reunion, on_delete=models.CASCADE, related_name="invitados")
    usuario = models.ForeignKey(User, on_delete=models.PROTECT, related_name="invitaciones_reunion")
    confirmado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["reunion", "usuario"], name="unique_reunion_staff_invite")]
