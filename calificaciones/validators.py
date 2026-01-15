# calificaciones/validators.py
import re
from django.core.exceptions import ValidationError

# Acepta 1-9, 10, TEA/TEP/TED y NO ENTREGADO (insensible a may/min, tolera "NO    ENTREGADO")
_PATTERN = re.compile(r'^(?:[1-9]|10|TEA|TEP|TED|NO\s+ENTREGADO)$', re.IGNORECASE)

def validate_calificacion(value: str):
    if value is None:
        raise ValidationError("La calificación es obligatoria.")
    val = str(value).strip().upper()
    if not _PATTERN.match(val):
        raise ValidationError("Solo se permiten 1–10, TEA, TEP, TED o NO ENTREGADO.")
