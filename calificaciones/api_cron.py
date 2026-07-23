from __future__ import annotations

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


def _check_secret(request) -> bool:
    expected = (getattr(settings, "CRON_SECRET", "") or "").strip()
    if not expected:
        return False
    provided = request.headers.get("X-Cron-Secret", "").strip()
    return provided == expected


@csrf_exempt
@require_http_methods(["POST"])
def cron_evaluar_alertas_academicas(request):
    if not _check_secret(request):
        return JsonResponse({"error": "No autorizado."}, status=401)

    try:
        from .models import Nota, Alumno, School
        from .alerts import (
            evaluar_alertas_notas_bulk,
            reconciliar_alertas_academicas,
            evaluar_alertas_inasistencia_por_alumnos,
        )

        total_notas_created = 0
        total_notas_closed = 0
        total_notas_evaluated = 0
        total_inas_created = 0
        schools_procesados = 0

        for school in School.objects.filter(is_active=True):
            # --- Alertas académicas (notas) ---
            notas_qs = (
                Nota.objects.filter(school=school)
                .select_related("alumno", "alumno__school_course")
                .order_by("alumno_id", "materia", "cuatrimestre", "-fecha", "-id")
            )

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

            if latest_by_key:
                result = evaluar_alertas_notas_bulk(
                    notas=list(latest_by_key.values()),
                    send_email=False,
                )
                recon = reconciliar_alertas_academicas(school=school)
                total_notas_created += int(result.get("created", 0))
                total_notas_closed += int(result.get("closed", 0)) + int(recon.get("cerradas", 0))
                total_notas_evaluated += int(result.get("evaluated", 0))

            # --- Alertas de inasistencias ---
            alumno_ids = list(
                Alumno.objects.filter(school=school).values_list("id", flat=True)
            )
            if alumno_ids:
                total_inas_created += evaluar_alertas_inasistencia_por_alumnos(
                    alumno_ids=alumno_ids,
                    tipo_asistencia="clases",
                )

            schools_procesados += 1

        return JsonResponse({
            "ok": True,
            "schools": schools_procesados,
            "notas_evaluated": total_notas_evaluated,
            "notas_alertas_created": total_notas_created,
            "notas_alertas_closed": total_notas_closed,
            "inasistencias_alertas_created": total_inas_created,
        })

    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=500)
