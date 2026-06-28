# calificaciones/api_alumnos/__init__.py
from ._views import (
    admin_importar_alumnos,
    admin_importar_alumnos_template,
    crear_alumno,
    vincular_mi_legajo,
    transferir_alumno,
    cursos_disponibles,
)
from ._helpers import _parse_import_file  # noqa: F401 — usado por tests

__all__ = [
    "admin_importar_alumnos",
    "admin_importar_alumnos_template",
    "crear_alumno",
    "vincular_mi_legajo",
    "transferir_alumno",
    "cursos_disponibles",
]
