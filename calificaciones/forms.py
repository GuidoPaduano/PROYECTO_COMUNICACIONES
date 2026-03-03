# calificaciones/forms.py
from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Evento, Nota, validate_calificacion_ext


def _parse_decimal_optional(value):
    if value in (None, ""):
        return None
    try:
        parsed = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if parsed < Decimal("1") or parsed > Decimal("10"):
        return None
    return parsed.quantize(Decimal("0.01"))


class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        if not email:
            return email
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Ya existe un usuario con ese correo.")
        return email


class NotaForm(forms.ModelForm):
    """Formulario HTML de carga de notas con esquema TEA/TEP/TED + numerica opcional."""

    resultado = forms.ChoiceField(
        required=False,
        choices=[("", "Selecciona..."), ("TEA", "Aprobado"), ("TEP", "Desaprobado"), ("TED", "Aplazado")],
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    nota_numerica = forms.DecimalField(
        required=False,
        min_value=1,
        max_value=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "1", "max": "10"}),
        help_text="Opcional. Entre 1 y 10.",
    )
    calificacion = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
        help_text="Campo legacy opcional para compatibilidad.",
    )

    class Meta:
        model = Nota
        fields = [
            "alumno",
            "materia",
            "tipo",
            "resultado",
            "nota_numerica",
            "calificacion",
            "cuatrimestre",
        ]
        widgets = {
            "alumno": forms.Select(attrs={"class": "form-control"}),
            "materia": forms.Select(attrs={"class": "form-control"}),
            "tipo": forms.Select(attrs={"class": "form-control"}),
            "cuatrimestre": forms.Select(attrs={"class": "form-control"}),
        }

    def clean_calificacion(self):
        value = (self.cleaned_data.get("calificacion") or "").strip().upper()
        if not value:
            return ""
        validate_calificacion_ext(value)
        return value

    def clean_resultado(self):
        value = (self.cleaned_data.get("resultado") or "").strip().upper()
        return value or None

    def clean(self):
        cleaned = super().clean()
        resultado = cleaned.get("resultado")
        nota_numerica = cleaned.get("nota_numerica")
        calificacion = (cleaned.get("calificacion") or "").strip().upper()

        if calificacion and calificacion in {"TEA", "TEP", "TED"} and not resultado:
            resultado = calificacion
            cleaned["resultado"] = resultado

        if calificacion and nota_numerica in (None, ""):
            parsed = _parse_decimal_optional(calificacion)
            if parsed is not None:
                cleaned["nota_numerica"] = parsed
                nota_numerica = parsed

        if not calificacion:
            if resultado:
                calificacion = resultado
            elif nota_numerica not in (None, ""):
                calificacion = str(nota_numerica).rstrip("0").rstrip(".")

        if not resultado and nota_numerica in (None, "") and not calificacion:
            raise forms.ValidationError("Debes cargar resultado o nota numerica.")

        cleaned["calificacion"] = calificacion
        return cleaned


class EventoForm(forms.ModelForm):
    class Meta:
        model = Evento
        fields = ["titulo", "descripcion", "fecha", "curso", "tipo_evento"]
        widgets = {
            "titulo": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej. Examen de Matematica"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "fecha": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "curso": forms.Select(attrs={"class": "form-control"}),
            "tipo_evento": forms.Select(attrs={"class": "form-control"}),
        }
