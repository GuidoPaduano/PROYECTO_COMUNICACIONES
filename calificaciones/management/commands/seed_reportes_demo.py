import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from calificaciones.models import Alumno, Asistencia, Nota


class Command(BaseCommand):
    help = "Carga datos aleatorios de notas y asistencias para probar reportes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--curso",
            type=str,
            default="",
            help="Curso a filtrar (ej: 1A). Si se omite, usa todos los cursos.",
        )
        parser.add_argument(
            "--months",
            type=int,
            default=4,
            help="Cantidad de meses hacia atras para generar datos.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=42,
            help="Seed para que los datos sean reproducibles.",
        )
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Elimina notas/asistencias previas de esos alumnos antes de generar.",
        )
        parser.add_argument(
            "--max-alumnos",
            type=int,
            default=12,
            help="Maximo de alumnos a procesar.",
        )
        parser.add_argument(
            "--notas-por-mes",
            type=int,
            default=3,
            help="Cantidad de notas por alumno por mes.",
        )
        parser.add_argument(
            "--asistencias-por-mes",
            type=int,
            default=6,
            help="Cantidad de asistencias por alumno por mes.",
        )

    def handle(self, *args, **options):
        curso = (options.get("curso") or "").strip()
        months = max(1, int(options.get("months") or 4))
        seed = int(options.get("seed") or 42)
        replace = bool(options.get("replace"))
        max_alumnos = max(1, int(options.get("max_alumnos") or 12))
        notas_por_mes = max(1, int(options.get("notas_por_mes") or 3))
        asistencias_por_mes = max(1, int(options.get("asistencias_por_mes") or 6))

        random.seed(seed)

        alumno_fields = {f.name for f in Alumno._meta.fields}
        if "apellido" in alumno_fields:
            alumnos_qs = Alumno.objects.all().order_by("curso", "apellido", "nombre")
        else:
            alumnos_qs = Alumno.objects.all().order_by("curso", "nombre")
        if curso:
            alumnos_qs = alumnos_qs.filter(curso__iexact=curso)

        alumnos = list(alumnos_qs[:max_alumnos])
        if not alumnos:
            self.stdout.write(self.style.WARNING("No hay alumnos para generar datos."))
            return

        if replace:
            alumno_ids = [a.id for a in alumnos]
            notas_deleted, _ = Nota.objects.filter(alumno_id__in=alumno_ids).delete()
            asist_deleted, _ = Asistencia.objects.filter(alumno_id__in=alumno_ids).delete()
            self.stdout.write(
                self.style.WARNING(
                    f"Datos previos eliminados. Notas: {notas_deleted}, Asistencias: {asist_deleted}"
                )
            )

        materias = [m[0] for m in Nota.MATERIAS]
        tipos_nota = [t[0] for t in Nota.TIPOS]
        tipos_asistencia = [t[0] for t in Asistencia._meta.get_field("tipo_asistencia").choices]

        today = timezone.localdate()
        start_month = today.replace(day=1)
        base_months = []
        for i in range(months):
            m = start_month - timedelta(days=30 * i)
            base_months.append(m.replace(day=1))
        base_months = sorted(set(base_months))

        notas_created = 0
        asist_created = 0
        asist_updated = 0

        for alumno in alumnos:
            for m in base_months:
                for _ in range(notas_por_mes):
                    day = random.randint(1, 28)
                    fecha = m.replace(day=day)
                    cuatrimestre = 1 if fecha.month <= 6 else 2
                    Nota.objects.create(
                        alumno=alumno,
                        materia=random.choice(materias),
                        tipo=random.choice(tipos_nota),
                        calificacion=f"{random.uniform(4.0, 10.0):.2f}",
                        cuatrimestre=cuatrimestre,
                        fecha=fecha,
                        observaciones="Dato de prueba para reportes",
                    )
                    notas_created += 1

                attendance_rows = []
                used_keys = set()
                for _ in range(asistencias_por_mes):
                    day = random.randint(1, 28)
                    fecha = m.replace(day=day)
                    tipo = random.choice(tipos_asistencia)
                    key = (fecha, tipo)
                    if key in used_keys:
                        continue
                    used_keys.add(key)

                    status = random.random()
                    if status < 0.10:
                        presente = False
                        tarde = False
                        justificada = random.random() < 0.45
                    elif status < 0.23:
                        presente = True
                        tarde = True
                        justificada = random.random() < 0.25
                    else:
                        presente = True
                        tarde = False
                        justificada = False

                    attendance_rows.append(
                        Asistencia(
                            alumno=alumno,
                            fecha=fecha,
                            tipo_asistencia=tipo,
                            presente=presente,
                            tarde=tarde,
                            justificada=justificada,
                            observacion="Dato de prueba",
                        )
                    )
                created_objs = Asistencia.objects.bulk_create(
                    attendance_rows,
                    ignore_conflicts=True,
                )
                asist_created += len(created_objs)
                asist_updated += max(0, len(attendance_rows) - len(created_objs))

        self.stdout.write(
            self.style.SUCCESS(
                f"OK. Alumnos: {len(alumnos)} | Notas creadas: {notas_created} | "
                f"Asistencias creadas: {asist_created} | Asistencias actualizadas: {asist_updated}"
            )
        )
