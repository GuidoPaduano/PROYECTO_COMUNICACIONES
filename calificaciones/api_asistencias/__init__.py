# calificaciones/api_asistencias/__init__.py
"""
Paquete api_asistencias — re-exporta los símbolos públicos que consume urls_api.py.
"""
from ._views import (
    preceptor_cursos,
    tipos_asistencia,
    registrar_asistencias,
    justificar_asistencia,
    firmar_asistencia,
    editar_detalle_asistencia,
    asistencias_por_alumno,
    asistencias_por_codigo,
    asistencias_por_curso_y_fecha,
)
from ._helpers import _bulk_upsert_asistencias  # noqa: F401 — usado por tests

__all__ = [
    "preceptor_cursos",
    "tipos_asistencia",
    "registrar_asistencias",
    "justificar_asistencia",
    "firmar_asistencia",
    "editar_detalle_asistencia",
    "asistencias_por_alumno",
    "asistencias_por_codigo",
    "asistencias_por_curso_y_fecha",
    "_bulk_upsert_asistencias",
]
