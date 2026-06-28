# calificaciones/api_eventos/__init__.py
from ._views import (
    preceptor_cursos,
    eventos_listar,
    eventos_crear,
    eventos_editar,
    eventos_eliminar,
    eventos_tipos,
    eventos_collection,
    eventos_detalle,
)

__all__ = [
    "preceptor_cursos",
    "eventos_listar",
    "eventos_crear",
    "eventos_editar",
    "eventos_eliminar",
    "eventos_tipos",
    "eventos_collection",
    "eventos_detalle",
]
