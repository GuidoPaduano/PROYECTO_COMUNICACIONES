from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator


def validate_calificacion_ext(value):
    """
    Este validador existe porque migraciones anteriores (0014/0015)
    lo referencian como calificaciones.models.validate_calificacion_ext.

    Acepta:
      - 1 a 10 (enteros o decimales con hasta 2 decimales)
      - TEA / TEP / TED
      - NO ENTREGADO
    """
    if value is None:
        raise ValidationError("La calificación no puede estar vacía.")

    s = str(value).strip()
    if not s:
        raise ValidationError("La calificación no puede estar vacía.")

    up = s.upper()

    allowed_text = {"TEA", "TEP", "TED", "NO ENTREGADO"}
    if up in allowed_text:
        return

    num_str = s.replace(",", ".")
    try:
        num = float(num_str)
    except Exception:
        raise ValidationError("Calificación inválida. Usá 1-10 o TEA/TEP/TED/NO ENTREGADO.")

    if not (1 <= num <= 10):
        raise ValidationError("La calificación numérica debe estar entre 1 y 10.")

    if "." in num_str:
        dec = num_str.split(".", 1)[1]
        if len(dec) > 2:
            raise ValidationError("La calificación puede tener como máximo 2 decimales.")


HEX_COLOR_VALIDATOR = RegexValidator(
    regex=r"^#[0-9A-Fa-f]{6}$",
    message="Usa un color hexadecimal con formato #RRGGBB.",
)
