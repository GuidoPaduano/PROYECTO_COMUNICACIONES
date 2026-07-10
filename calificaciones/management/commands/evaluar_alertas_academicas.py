"""
Comando de escaneo diario de alertas académicas.

Recorre todas las notas activas del sistema, toma la nota más reciente
por combinación (alumno, materia, cuatrimestre) y evalúa si corresponde
crear o cerrar una alerta académica.

Uso:
    python manage.py evaluar_alertas_academicas
    python manage.py evaluar_alertas_academicas --school-id 3
    python manage.py evaluar_alertas_academicas --dry-run
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Escaneo diario: evalúa alertas académicas para todos los alumnos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school-id",
            type=int,
            default=None,
            help="Limitar el escaneo a un colegio específico.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra cuántas combinaciones se evaluarían sin crear ni cerrar alertas.",
        )

    def handle(self, *args, **options):
        from calificaciones.models import Nota, School
        from calificaciones.alerts import evaluar_alertas_notas_bulk, reconciliar_alertas_academicas

        school_id = options["school_id"]
        dry_run = options["dry_run"]
        hoy = timezone.localdate()

        self.stdout.write(f"[{hoy}] Iniciando escaneo de alertas académicas{'  (DRY RUN)' if dry_run else ''}...")

        schools = School.objects.filter(is_active=True)
        if school_id is not None:
            schools = schools.filter(pk=school_id)

        total_created = 0
        total_closed = 0
        total_evaluated = 0

        for school in schools:
            result = self._procesar_school(school, dry_run=dry_run)
            total_created += result["created"]
            total_closed += result["closed"]
            total_evaluated += result["evaluated"]
            if result["evaluated"] > 0:
                self.stdout.write(
                    f"  {school.name}: {result['evaluated']} combinaciones, "
                    f"{result['created']} alertas nuevas, {result['closed']} cerradas."
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Listo. Total: {total_evaluated} evaluadas, "
                f"{total_created} alertas nuevas, {total_closed} cerradas."
            )
        )

    def _procesar_school(self, school, *, dry_run: bool) -> dict:
        from calificaciones.models import Nota
        from calificaciones.alerts import evaluar_alertas_notas_bulk, reconciliar_alertas_academicas

        # 1. Traer la nota más reciente por (alumno, materia, cuatrimestre)
        #    para todos los alumnos del colegio.
        notas_qs = (
            Nota.objects.filter(school=school)
            .select_related("alumno", "alumno__school_course")
            .order_by("alumno_id", "materia", "cuatrimestre", "-fecha", "-id")
        )

        # Deduplicar en Python para quedarnos con la más reciente por clave
        latest_by_key: dict[tuple, object] = {}
        for nota in notas_qs:
            alumno_id = getattr(nota, "alumno_id", None)
            materia = str(getattr(nota, "materia", "") or "").strip()
            cuatrimestre = getattr(nota, "cuatrimestre", None)
            if alumno_id is None or not materia:
                continue
            key = (alumno_id, materia, cuatrimestre)
            if key not in latest_by_key:
                latest_by_key[key] = nota

        if not latest_by_key:
            return {"created": 0, "closed": 0, "evaluated": 0}

        if dry_run:
            return {"created": 0, "closed": 0, "evaluated": len(latest_by_key)}

        # 2. Evaluar en batch (una sola consulta extra de notas en ventana)
        result = evaluar_alertas_notas_bulk(
            notas=list(latest_by_key.values()),
            send_email=False,
        )

        # 3. Cerrar alertas cuyas condiciones ya no se cumplen
        recon = reconciliar_alertas_academicas(school=school)

        return {
            "created": int(result.get("created", 0)),
            "closed": int(result.get("closed", 0)) + int(recon.get("cerradas", 0)),
            "evaluated": int(result.get("evaluated", 0)),
        }
