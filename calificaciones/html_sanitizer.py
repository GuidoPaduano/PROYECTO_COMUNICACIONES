"""
Sanitización de HTML para contenido generado por usuarios (mensajes, etc.).
Permite únicamente un subconjunto seguro de etiquetas y atributos.
"""

import bleach

_ALLOWED_TAGS = [
    "p", "br", "b", "i", "u", "strong", "em",
    "ul", "ol", "li",
    "a",
    "span", "div",
]

_ALLOWED_ATTRS = {
    "a": ["href"],
}

_ALLOWED_PROTOCOLS = ["https", "http", "mailto"]


def sanitize_html(html: str) -> str:
    """Limpia HTML conservando formato básico y eliminando todo lo ejecutable."""
    if not html:
        return ""
    return bleach.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        protocols=_ALLOWED_PROTOCOLS,
        strip=True,
        strip_comments=True,
    )
