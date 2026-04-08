# calificaciones/forms.py
from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Evento, Nota, School, validate_calificacion_ext
from .schools import (
    DEFAULT_SCHOOL_ACCENT_COLOR,
    DEFAULT_SCHOOL_LOGO_URL,
    DEFAULT_SCHOOL_PRIMARY_COLOR,
)
from .utils_cursos import get_school_course_by_id


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
        help_text="Campo de texto opcional.",
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
    school_course_id = forms.ChoiceField(
        required=True,
        label="Curso",
        choices=[],
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.selected_school = school or getattr(getattr(self, "instance", None), "school", None)
        choices = [("", "Selecciona un curso...")]
        if self.selected_school is not None:
            try:
                choices.extend(
                    [
                        (str(course.id), str(course.name))
                        for course in self.selected_school.courses.filter(is_active=True).order_by("sort_order", "id")
                    ]
                )
            except Exception:
                pass
        self.fields["school_course_id"].choices = choices
        if getattr(getattr(self, "instance", None), "school_course_id", None):
            self.fields["school_course_id"].initial = str(self.instance.school_course_id)

    class Meta:
        model = Evento
        fields = ["titulo", "descripcion", "fecha", "tipo_evento"]
        widgets = {
            "titulo": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej. Examen de Matematica"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "fecha": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "tipo_evento": forms.Select(attrs={"class": "form-control"}),
        }

    def clean_school_course_id(self):
        school_course_id = (self.cleaned_data.get("school_course_id") or "").strip()
        school_course = get_school_course_by_id(
            school_course_id,
            school=self.selected_school,
            include_inactive=True,
        )
        if school_course is None:
            raise forms.ValidationError("Selecciona un curso válido.")
        self.cleaned_data["school_course"] = school_course
        return str(school_course.id)

    def save(self, commit=True):
        instance = super().save(commit=False)
        school_course = self.cleaned_data.get("school_course")
        if school_course is not None:
            if getattr(instance, "school_id", None) is None and self.selected_school is not None:
                instance.school = self.selected_school
            instance.school_course = school_course
            instance.curso = school_course.code
        if commit:
            instance.save()
        return instance


class SchoolAdminForm(forms.ModelForm):
    class Meta:
        model = School
        fields = "__all__"
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ej. Escuela Tecnova"}),
            "short_name": forms.TextInput(attrs={"placeholder": "Ej. Tecnova"}),
            "slug": forms.TextInput(attrs={"placeholder": "ej. escuela-tecnova"}),
            "logo_url": forms.TextInput(attrs={"placeholder": DEFAULT_SCHOOL_LOGO_URL}),
            "primary_color": forms.TextInput(attrs={"placeholder": DEFAULT_SCHOOL_PRIMARY_COLOR}),
            "accent_color": forms.TextInput(attrs={"placeholder": DEFAULT_SCHOOL_ACCENT_COLOR}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["short_name"].help_text = "Nombre corto para sidebar y login."
        self.fields["logo_url"].help_text = "Acepta rutas relativas como /imagenes/logo.png o URLs completas."
        self.fields["primary_color"].help_text = "Color principal en formato #RRGGBB."
        self.fields["accent_color"].help_text = "Color de acento en formato #RRGGBB."

    def clean_short_name(self):
        return (self.cleaned_data.get("short_name") or "").strip()

    def clean_logo_url(self):
        return (self.cleaned_data.get("logo_url") or "").strip()

    def _clean_hex_field(self, field_name):
        value = (self.cleaned_data.get(field_name) or "").strip()
        return value.upper()

    def clean_primary_color(self):
        return self._clean_hex_field("primary_color")

    def clean_accent_color(self):
        return self._clean_hex_field("accent_color")
