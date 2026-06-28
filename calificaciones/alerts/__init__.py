"""
alerts package — re-exports all public symbols from both domain submodules
so that existing import paths (`from .alerts import ...` / `from calificaciones.alerts import ...`)
continue to work without any changes in external files.
"""

from ._academic import (
    nota_es_ted,
    reconciliar_alertas_academicas,
    evaluar_alerta_nota,
    evaluar_alertas_notas_bulk,
)

from ._inasistencias import (
    evaluar_alerta_inasistencia,
    evaluar_alertas_inasistencia_por_alumnos,
)

__all__ = [
    # academic
    "nota_es_ted",
    "reconciliar_alertas_academicas",
    "evaluar_alerta_nota",
    "evaluar_alertas_notas_bulk",
    # inasistencias
    "evaluar_alerta_inasistencia",
    "evaluar_alertas_inasistencia_por_alumnos",
]
