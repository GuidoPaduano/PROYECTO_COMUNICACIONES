# calificaciones/forms_user.py
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

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
