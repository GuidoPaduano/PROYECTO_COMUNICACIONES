from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)


def _from_email() -> str:
    return (getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip()


def send_resend_email(*, to_email: str, subject: str, text: str | None = None, html: str | None = None) -> bool:
    from_email = _from_email()
    to_email = (to_email or "").strip()

    if not from_email or not to_email:
        logger.warning("Email not sent: missing from_email or to_email")
        return False

    try:
        msg = EmailMultiAlternatives(
            subject=(subject or "Mensaje").strip(),
            body=text or "",
            from_email=from_email,
            to=[to_email],
        )
        if html:
            msg.attach_alternative(html, "text/html")
        msg.send()
        return True
    except Exception:
        logger.exception("Email send failed to=%s subject=%s", to_email, subject)
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
