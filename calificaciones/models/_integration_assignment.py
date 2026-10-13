from django.conf import settings
from django.db import models


class IntegrationStudentAssignment(models.Model):
    school = models.ForeignKey('School', on_delete=models.PROTECT)
    alumno = models.ForeignKey('Alumno', on_delete=models.CASCADE, related_name='integration_assignments')
    maestra = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='integration_students')
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['alumno', 'maestra'], name='unique_integration_student_teacher')]
