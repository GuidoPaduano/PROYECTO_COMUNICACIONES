from __future__ import annotations

import logging
import time

from django.conf import settings

logger = logging.getLogger("calificaciones.request")


class RequestLifecycleLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.enabled = bool(getattr(settings, "REQUEST_LIFECYCLE_LOGGING", False))

    def __call__(self, request):
        if not self.enabled:
            return self.get_response(request)

        started = time.monotonic()
        method = getattr(request, "method", "")
        path = getattr(request, "path", "")
        logger.warning("REQUEST_START method=%s path=%s", method, path)
        try:
            response = self.get_response(request)
        except Exception:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            logger.exception(
                "REQUEST_ERROR method=%s path=%s elapsed_ms=%s",
                method,
                path,
                elapsed_ms,
            )
            raise

        elapsed_ms = int((time.monotonic() - started) * 1000)
        logger.warning(
            "REQUEST_END method=%s path=%s status=%s elapsed_ms=%s",
            method,
            path,
            getattr(response, "status_code", None),
            elapsed_ms,
        )
        return response
