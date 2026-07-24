from __future__ import annotations

import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .resend_email import send_resend_email

logger = logging.getLogger(__name__)

CONTACTO_EMAIL = "contacto@alumnix.com.ar"


@csrf_exempt
@require_POST
def contacto_landing(request):
    try:
        payload = json.loads(request.body or b"{}")
    except Exception:
        return JsonResponse({"detail": "JSON inválido."}, status=400)

    name = (payload.get("name") or "").strip()
    school = (payload.get("school") or "").strip()
    email = (payload.get("email") or "").strip()
    students = str(payload.get("students") or "").strip()
    message = (payload.get("message") or "").strip()

    if not name or not email:
        return JsonResponse({"detail": "Nombre y email son requeridos."}, status=400)

    lines = [
        f"Nombre: {name}",
        f"Email: {email}",
    ]
    if school:
        lines.append(f"Institución: {school}")
    if students:
        lines.append(f"Alumnos aproximados: {students}")
    if message:
        lines.append(f"\nMensaje:\n{message}")

    text_body = "\n".join(lines)

    html_body = f"""
<p><strong>Nombre:</strong> {name}</p>
<p><strong>Email:</strong> {email}</p>
{"<p><strong>Institución:</strong> " + school + "</p>" if school else ""}
{"<p><strong>Alumnos aproximados:</strong> " + students + "</p>" if students else ""}
{"<p><strong>Mensaje:</strong></p><p>" + message.replace(chr(10), "<br>") + "</p>" if message else ""}
""".strip()

    ok = send_resend_email(
        to_email=CONTACTO_EMAIL,
        subject=f"Consulta desde la landing: {school or name}",
        text=text_body,
        html=html_body,
    )

    if not ok:
        logger.error("api_contacto: send_resend_email returned False for email=%s", email)
        return JsonResponse({"detail": "No se pudo enviar el mensaje. Intentá más tarde."}, status=502)

    return JsonResponse({"ok": True})
