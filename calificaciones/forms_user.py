# calificaciones/forms_user.py
from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.models import User
from django.db.models import Q

from .models import Alumno

class CustomUserCreationForm(UserCreationForm):
    role = forms.ChoiceField(
        label='Rol',
        required=True,  # ← obligatorio
        choices=[
            ('Alumnos', 'Alumno/a'),
            ('Padres', 'Padre/Madre/Tutor'),
            ('Profesores', 'Profesor/a'),
            ('Preceptores', 'Preceptor/a'),
        ],
        help_text="Asigna automáticamente el usuario a este grupo."
    )

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


class CustomUserChangeForm(UserChangeForm):
    curso = forms.ChoiceField(
        choices=[("", "---------")] + list(Alumno.CURSOS),
        required=False,
        label="Curso",
        help_text="Filtra la lista de alumnos por curso.",
    )
    alumno = forms.ModelChoiceField(
        queryset=Alumno.objects.none(),
        required=False,
        label="Alumno vinculado",
        help_text="Selecciona un alumno existente para vincular a este usuario.",
    )

    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = getattr(self, "instance", None)
        base_qs = Alumno.objects.all()
        selected_course = ""
        if user and user.pk:
            base_qs = base_qs.filter(Q(usuario__isnull=True) | Q(usuario=user))
            try:
                linked = Alumno.objects.filter(usuario=user).first()
            except Exception:
                linked = None
            if linked:
                self.fields["alumno"].initial = linked
                selected_course = getattr(linked, "curso", "") or ""
        else:
            base_qs = base_qs.filter(usuario__isnull=True)

        selected_course = (self.data.get("curso") or selected_course or "").strip()
        if selected_course:
            base_qs = base_qs.filter(curso=selected_course)
        self.fields["curso"].initial = selected_course
        self.fields["alumno"].queryset = base_qs.order_by("curso", "nombre")

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        if not email:
            return email
        qs = User.objects.filter(email__iexact=email)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ya existe un usuario con ese correo.")
        return email
