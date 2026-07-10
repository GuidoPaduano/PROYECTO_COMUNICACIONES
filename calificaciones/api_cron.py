from __future__ import annotations

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


def _check_secret(request) -> bool:
    expected = (getattr(settings, "CRON_SECRET", "") or "").strip()
    if not expected:
        return False
    provided = (
        request.headers.get("X-Cron-Secret", "")
        or request.GET.get("secret", "")
    ).strip()
    return provided == expected


@csrf_exempt
@require_http_methods(["GET", "POST"])
def cron_evaluar_alertas_academicas(request):
    if not _check_secret(request):
        return JsonResponse({"error": "No autorizado."}, status=401)

    try:
        from .models import Nota, School
        from .alerts import evaluar_alertas_notas_bulk, reconciliar_alertas_academicas

        total_created = 0
        total_closed = 0
        total_evaluated = 0
        schools_procesados = 0

        for school in School.objects.filter(is_active=True):
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

            if not latest_by_key:
                continue

            result = evaluar_alertas_notas_bulk(
                notas=list(latest_by_key.values()),
                send_email=False,
            )
            recon = reconciliar_alertas_academicas(school=school)

            total_created += int(result.get("created", 0))
            total_closed += int(result.get("closed", 0)) + int(recon.get("cerradas", 0))
            total_evaluated += int(result.get("evaluated", 0))
            schools_procesados += 1

        return JsonResponse({
            "ok": True,
            "schools": schools_procesados,
            "evaluated": total_evaluated,
            "created": total_created,
            "closed": total_closed,
        })

    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=500)
