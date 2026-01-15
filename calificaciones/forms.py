# calificaciones/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Nota, Evento
from .validators import validate_calificacion


class CustomUserCreationForm(UserCreationForm):
    """
    Formulario mínimo para satisfacer el import desde admin.py.
    Ajustá los fields si tu admin necesita más datos.
    """
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")  # lo básico; ajustá si hace falta


class NotaForm(forms.ModelForm):
    """
    Form para la vista HTML de 'agregar_nota'.
    - Muestra SELECT para calificación (incluye “No entregado”).
    - Normaliza la calificación a mayúsculas antes de guardar.
    - Valida contra el validador del proyecto (1–10, TEA/TEP/TED o NO ENTREGADO).
    """

    # Tomamos las opciones desde el modelo si existen; si no, fallback estático
    try:
        _CALIF_CHOICES = Nota.CALIFICACION_CHOICES
    except Exception:
        _CALIF_CHOICES = (
            [(str(n), str(n)) for n in range(1, 11)]
            + [("TEA", "TEA"), ("TEP", "TEP"), ("TED", "TED"), ("NO ENTREGADO", "No entregado")]
        )

    calificacion = forms.ChoiceField(
        choices=_CALIF_CHOICES,
        required=True,
        help_text="Valores permitidos: 1–10, TEA, TEP, TED o No entregado.",
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    class Meta:
        model = Nota
        # Nota: no incluyo 'fecha' porque tu modelo la maneja con auto_now_add
        fields = ["alumno", "materia", "tipo", "calificacion", "cuatrimestre"]
        widgets = {
            "alumno": forms.Select(attrs={"class": "form-control"}),
            "materia": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej. Matemática"}),
            "tipo": forms.Select(attrs={"class": "form-control"}),          # usa choices del modelo
            "cuatrimestre": forms.Select(attrs={"class": "form-control"}),  # usa choices del modelo
        }

    def clean_calificacion(self):
        """
        Normaliza a mayúsculas y valida.
        Acepta “NO ENTREGADO” explícitamente y delega el resto al validador del proyecto.
        """
        val = (self.cleaned_data.get("calificacion") or "").strip()
        up = val.upper()
        if up == "NO ENTREGADO":
            return "NO ENTREGADO"
        # El validador del proyecto ya contempla 1–10/TEA/TEP/TED (y si lo actualizaste, también NO ENTREGADO)
        validate_calificacion(up)
        return up

    def clean_materia(self):
        m = (self.cleaned_data.get("materia") or "").strip()
        if not m:
            raise forms.ValidationError("La materia es obligatoria.")
        return m


class EventoForm(forms.ModelForm):
    """
    Form para crear/editar eventos desde las vistas HTML (calendario).
    Lo movemos acá para centralizar formularios.
    """
    class Meta:
        model = Evento
        fields = ["titulo", "descripcion", "fecha", "curso", "tipo_evento"]
        widgets = {
            "titulo": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej. Examen de Matemática"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "fecha": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "curso": forms.Select(attrs={"class": "form-control"}),        # usa Alumno.CURSOS
            "tipo_evento": forms.Select(attrs={"class": "form-control"}),  # usa choices del modelo
        }
