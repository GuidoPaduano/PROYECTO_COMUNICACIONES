from __future__ import annotations

import json
import logging
import os
from urllib import error, request

from django.conf import settings

logger = logging.getLogger(__name__)


def _api_key() -> str:
    key = getattr(settings, "RESEND_API_KEY_EFFECTIVE", "") or ""
    if key:
        return key
    key = getattr(settings, "RESEND_API_KEY", "") or ""
    if key:
        return key
    return os.environ.get("RESEND_API_KEY", "") or ""


def _from_email() -> str:
    return (getattr(settings, "RESEND_FROM_EMAIL", "") or os.environ.get("RESEND_FROM_EMAIL", "") or "").strip()


def _timeout_seconds() -> int:
    try:
        return int(os.environ.get("RESEND_TIMEOUT", "10"))
    except Exception:
        return 10


def send_resend_email(*, to_email: str, subject: str, text: str | None = None, html: str | None = None) -> bool:
    api_key = _api_key()
    from_email = _from_email()
    to_email = (to_email or "").strip()

    if not api_key or not from_email or not to_email:
        return False

    payload: dict[str, object] = {
        "from": from_email,
        "to": [to_email],
        "subject": (subject or "Mensaje").strip(),
    }
    if text:
        payload["text"] = text
    if html:
        payload["html"] = html

    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    req = request.Request("https://api.resend.com/emails", data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=_timeout_seconds()) as resp:
            return 200 <= resp.status < 300
    except error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        logger.warning("Resend HTTPError status=%s body=%s", exc.code, body[:500])
    except Exception:
        logger.exception("Resend send failed")

    return False


def send_message_email(*, to_email: str, subject: str, content: str, actor_label: str = "") -> bool:
    lines: list[str] = []
    actor_label = (actor_label or "").strip()
    content = (content or "").strip()

    if actor_label:
        lines.append(f"De: {actor_label}")

    if content:
        if lines:
            lines.append("")
        lines.append(content)

    if lines:
        lines.append("")
    lines.append("Ingresa al sistema para leer y responder.")

    return send_resend_email(
        to_email=to_email,
        subject=(subject or "Nuevo mensaje").strip(),
        text="\n".join(lines),
    )
