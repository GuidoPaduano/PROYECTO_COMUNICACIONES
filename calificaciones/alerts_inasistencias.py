# Compatibility shim — real implementation lives in alerts/_inasistencias.py
from .alerts._inasistencias import (  # noqa: F401
    evaluar_alerta_inasistencia,
    evaluar_alertas_inasistencia_por_alumnos,
)
