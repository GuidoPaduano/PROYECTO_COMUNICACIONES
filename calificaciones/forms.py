from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User, Group

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

class CustomUserCreationForm(UserCreationForm):
    role = forms.ChoiceField(
        choices=[
            ('Padres', 'Padre'),
            ('Profesores', 'Profesor'),
            ('Alumnos', 'Alumno'),
        ],
        label='Rol del usuario',
        required=True,
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2', 'role')