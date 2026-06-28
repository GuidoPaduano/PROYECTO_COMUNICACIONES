"""
Utilidades compartidas entre los módulos de API.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from django.http import QueryDict
from rest_framework.response import Response


def _first_scalar(v: Any) -> Any:
    """Si viene ['x'] (QueryDict/dict(request.data)), devolvé 'x'."""
    if isinstance(v, (list, tuple)):
        return v[0] if v else None
    return v


def _try_parse_json(value: Any) -> Any:
    """Si value es string JSON, intenta parsearlo."""
    if not isinstance(value, str):
        return value
    s = value.strip()
    if not s:
        return value
    if not (s.startswith("{") or s.startswith("[") or s.startswith('"')):
        return value
    try:
        return json.loads(s)
    except Exception:
        return value


def _coerce_json(request) -> Dict[str, Any]:
    """Lee JSON del request incluso cuando request.data viene vacío o es form-data.

    Normaliza QueryDict a {k: value_scalar} para que campos como 'curso' no sean ['1A'].
    """
    try:
        if getattr(request, "data", None) is not None:
            data = request.data

            if isinstance(data, QueryDict):
                out: Dict[str, Any] = {}
                for k in list(data.keys()):
                    out[k] = _first_scalar(data.get(k))
                return out

            if isinstance(data, dict):
                return dict(data)
    except Exception:
        pass

    try:
        raw = (request.body or b"").decode("utf-8")
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _ok_response(payload: Dict[str, Any], status: int = 200) -> Response:
    return Response(payload, status=status)


def _err(detail: str, status: int = 400, extra: Optional[Dict[str, Any]] = None) -> Response:
    body: Dict[str, Any] = {"detail": detail}
    if extra:
        body.update(extra)
    return Response(body, status=status)
