# calificaciones/management/commands/import_preceptor_cursos_from_groups.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from calificaciones.models import Alumno
from calificaciones.models_preceptores import PreceptorCurso

User = get_user_model()

class Command(BaseCommand):
    help = "Crea PreceptorCurso a partir de grupos cuyo nombre coincide con un código de curso."

    def handle(self, *args, **options):
        codigos_validos = set(c for (c, _) in Alumno.CURSOS)
        creados, ya_estaban = 0, 0

        for u in User.objects.all():
            grupos = set(u.groups.values_list("name", flat=True))
            cursos = grupos & codigos_validos
            for c in cursos:
                obj, created = PreceptorCurso.objects.get_or_create(preceptor=u, curso=c)
                if created:
                    creados += 1
                else:
                    ya_estaban += 1

        self.stdout.write(self.style.SUCCESS(
            f"Asignaciones creadas: {creados}. Ya existentes: {ya_estaban}."
        ))
