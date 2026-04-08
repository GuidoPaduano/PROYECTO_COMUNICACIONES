# calificaciones/forms_user.py
from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.models import User
from django.db.models import Q

from .course_access import build_course_membership_q
from .models import Alumno, School, resolve_school_course_for_value
from .schools import get_request_school, scope_queryset_to_school
from .utils_cursos import get_school_course_choices

class CustomUserCreationForm(UserCreationForm):
    role = forms.ChoiceField(
        label='Rol',
        required=True,  # ← obligatorio
        choices=[
            ('Alumnos', 'Alumno/a'),
            ('Padres', 'Padre/Madre/Tutor'),
            ('Profesores', 'Profesor/a'),
            ('Preceptores', 'Preceptor/a'),
            ('Directivos', 'Directivo/a'),
        ],
        help_text="Asigna automáticamente el usuario a este grupo."
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        if not email:
            return email
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Ya existe un usuario con ese correo.")
        return email


class CustomUserChangeForm(UserChangeForm):
    school = forms.ModelChoiceField(
        queryset=School.objects.none(),
        required=False,
        label="Colegio",
        help_text="Filtra la lista de alumnos por colegio.",
    )
    curso = forms.ChoiceField(
        choices=[("", "---------")],
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

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)
        user = getattr(self, "instance", None)
        self.fields["school"].queryset = School.objects.order_by("name")
        base_qs = Alumno.objects.all()
        selected_school = None
        selected_course = ""
        linked = None

        if user and user.pk:
            base_qs = base_qs.filter(Q(usuario__isnull=True) | Q(usuario=user))
            try:
                linked = Alumno.objects.select_related("school").filter(usuario=user).first()
            except Exception:
                linked = None
            if linked:
                self.fields["alumno"].initial = linked
                selected_school = getattr(linked, "school", None)
                selected_course = getattr(linked, "curso", "") or ""
        else:
            base_qs = base_qs.filter(usuario__isnull=True)

        raw_school = ""
        try:
            raw_school = (self.data.get("school") or "").strip()
        except Exception:
            raw_school = ""

        if raw_school:
            try:
                selected_school = self.fields["school"].queryset.filter(pk=int(raw_school)).first()
            except Exception:
                selected_school = None
        elif selected_school is None and request is not None:
            selected_school = get_request_school(request)

        self.fields["school"].initial = getattr(selected_school, "pk", None)
        self.fields["curso"].choices = [("", "---------")] + list(get_school_course_choices(school=selected_school))

        if selected_school is not None:
            base_qs = scope_queryset_to_school(base_qs, selected_school, include_null=False)

        selected_course = (self.data.get("curso") or selected_course or "").strip()
        if selected_course:
            school_course = resolve_school_course_for_value(school=selected_school, curso=selected_course) if selected_school is not None else None
            course_q = build_course_membership_q(
                school_course_id=getattr(school_course, "id", None),
                course_code=selected_course,
                school_course_field="school_course",
                code_field="curso",
            )
            base_qs = base_qs.filter(course_q) if course_q is not None else base_qs.none()
        self.fields["curso"].initial = selected_course
        self.fields["alumno"].queryset = base_qs.order_by("curso", "apellido", "nombre", "id_alumno")

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

    def clean(self):
        cleaned = super().clean()
        school = cleaned.get("school")
        curso = (cleaned.get("curso") or "").strip()
        alumno = cleaned.get("alumno")

        if alumno is not None and school is not None and getattr(alumno, "school_id", None) != getattr(school, "id", None):
            self.add_error("alumno", "El alumno seleccionado no pertenece al colegio elegido.")

        alumno_course = getattr(getattr(alumno, "school_course", None), "code", None) or (getattr(alumno, "curso", "") or "").strip()
        if alumno is not None and curso and alumno_course != curso:
            self.add_error("alumno", "El alumno seleccionado no pertenece al curso elegido.")

        return cleaned
