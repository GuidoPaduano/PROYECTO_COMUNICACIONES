import logging
from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User, Group

from .forms_user import CustomUserCreationForm, CustomUserChangeForm
from .models import (
    Alumno,
    Nota,
    Sancion,
    Asistencia,
)
from .models_preceptores import PreceptorCurso, ProfesorCurso

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Alumno
# ─────────────────────────────────────────────────────────────
@admin.register(Alumno)
class AlumnoAdmin(admin.ModelAdmin):
    list_display = ("apellido", "nombre", "id_alumno", "curso", "padre")
    list_filter = ("curso",)
    search_fields = ("nombre", "apellido", "id_alumno")
    ordering = ("curso", "apellido", "nombre")


# ─────────────────────────────────────────────────────────────
# Nota
# ─────────────────────────────────────────────────────────────
@admin.register(Nota)
class NotaAdmin(admin.ModelAdmin):
    list_display = ("alumno", "materia", "tipo", "calificacion", "cuatrimestre", "fecha")
    list_filter = ("materia", "tipo", "cuatrimestre", "fecha", "alumno__curso")
    search_fields = ("alumno__nombre", "alumno__apellido", "alumno__id_alumno", "observaciones")
    ordering = ("-fecha", "-id")
    date_hierarchy = "fecha"
    list_select_related = ("alumno",)
    autocomplete_fields = ("alumno",)


# ─────────────────────────────────────────────────────────────
# Sanción (FIX: el admin estaba apuntando a campos que NO existen)
# ─────────────────────────────────────────────────────────────
@admin.register(Sancion)
class SancionAdmin(admin.ModelAdmin):
    list_display = ("alumno", "curso_del_alumno", "tipo", "fecha", "docente")
    list_filter = ("tipo", "fecha", "alumno__curso")
    search_fields = (
        "motivo",
        "detalle",
        "docente",
        "alumno__nombre",
        "alumno__apellido",
        "alumno__id_alumno",
    )
    ordering = ("-fecha", "-id")
    date_hierarchy = "fecha"
    list_select_related = ("alumno",)
    autocomplete_fields = ("alumno",)

    @admin.display(description="Curso", ordering="alumno__curso")
    def curso_del_alumno(self, obj):
        try:
            return obj.alumno.curso
        except Exception:
            return ""


# ─────────────────────────────────────────────────────────────
# Asistencia (nuevo modelo con tipo_asistencia)
# ─────────────────────────────────────────────────────────────
@admin.register(Asistencia)
class AsistenciaAdmin(admin.ModelAdmin):
    list_display = ("alumno", "curso_del_alumno", "fecha", "tipo_asistencia", "presente", "tarde", "creado_por")
    list_filter = ("tipo_asistencia", "fecha", "presente", "tarde", "alumno__curso")
    search_fields = (
        "alumno__nombre",
        "alumno__apellido",
        "alumno__id_alumno",
        "observacion",
    )
    ordering = ("-fecha", "-id")
    date_hierarchy = "fecha"
    list_select_related = ("alumno", "creado_por")
    autocomplete_fields = ("alumno",)

    @admin.display(description="Curso", ordering="alumno__curso")
    def curso_del_alumno(self, obj):
        try:
            return obj.alumno.curso
        except Exception:
            return ""


# ====================================================================================
# Preceptor / Profesor: asignaciones de cursos (filtrar usuarios por grupo)
# ====================================================================================
@admin.register(PreceptorCurso)
class PreceptorCursoAdmin(admin.ModelAdmin):
    list_display = ("preceptor", "cursos_asignados", "cantidad_cursos")
    list_filter = ("curso",)
    search_fields = ("preceptor__username", "preceptor__first_name", "preceptor__last_name")
    autocomplete_fields = ("preceptor",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        try:
            return qs.order_by("preceptor_id").distinct("preceptor_id")
        except Exception:
            return qs

    @admin.display(description="Cursos")
    def cursos_asignados(self, obj):
        try:
            cursos = (
                PreceptorCurso.objects.filter(preceptor=obj.preceptor)
                .values_list("curso", flat=True)
                .order_by("curso")
            )
            return ", ".join(cursos)
        except Exception:
            return ""

    @admin.display(description="Cantidad")
    def cantidad_cursos(self, obj):
        try:
            return PreceptorCurso.objects.filter(preceptor=obj.preceptor).count()
        except Exception:
            return 0

    def get_form(self, request, obj=None, **kwargs):
        class _PreceptorCursoForm(forms.ModelForm):
            class Meta:
                model = PreceptorCurso
                fields = "__all__"

            def __init__(self, *args, **inner_kwargs):
                super().__init__(*args, **inner_kwargs)
                self.fields["preceptor"].queryset = User.objects.filter(
                    groups__name__in=["Preceptores", "Preceptor"]
                ).distinct()

        kwargs["form"] = _PreceptorCursoForm
        return super().get_form(request, obj, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "preceptor":
            kwargs["queryset"] = User.objects.filter(
                groups__name__in=["Preceptores", "Preceptor"]
            ).distinct()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(ProfesorCurso)
class ProfesorCursoAdmin(admin.ModelAdmin):
    list_display = ("profesor", "cursos_asignados", "cantidad_cursos")
    list_filter = ("curso",)
    search_fields = ("profesor__username", "profesor__first_name", "profesor__last_name")
    autocomplete_fields = ("profesor",)

    def get_form(self, request, obj=None, **kwargs):
        class _ProfesorCursoForm(forms.ModelForm):
            class Meta:
                model = ProfesorCurso
                fields = "__all__"

            def __init__(self, *args, **inner_kwargs):
                super().__init__(*args, **inner_kwargs)
                self.fields["profesor"].queryset = User.objects.filter(
                    groups__name__in=["Profesores", "Profesor"]
                ).distinct()

        kwargs["form"] = _ProfesorCursoForm
        return super().get_form(request, obj, **kwargs)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        try:
            return qs.order_by("profesor_id").distinct("profesor_id")
        except Exception:
            return qs

    @admin.display(description="Cursos")
    def cursos_asignados(self, obj):
        try:
            cursos = (
                ProfesorCurso.objects.filter(profesor=obj.profesor)
                .values_list("curso", flat=True)
                .order_by("curso")
            )
            return ", ".join(cursos)
        except Exception:
            return ""

    @admin.display(description="Cantidad")
    def cantidad_cursos(self, obj):
        try:
            return ProfesorCurso.objects.filter(profesor=obj.profesor).count()
        except Exception:
            return 0

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "profesor":
            kwargs["queryset"] = User.objects.filter(
                groups__name__in=["Profesores", "Profesor"]
            ).distinct()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# ─────────────────────────────────────────────────────────────
# User
# ─────────────────────────────────────────────────────────────
class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    fieldsets = UserAdmin.fieldsets + (
        ("Vinculacion", {"fields": ("curso", "alumno")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "email", "password1", "password2", "role"),
        }),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        alumno = getattr(form, "cleaned_data", {}).get("alumno")
        if alumno is not None:
            try:
                Alumno.objects.filter(usuario=obj).exclude(pk=alumno.pk).update(usuario=None)
            except Exception:
                pass
            try:
                if alumno:
                    if alumno.usuario_id != obj.id:
                        alumno.usuario = obj
                        alumno.save(update_fields=["usuario"])
                else:
                    Alumno.objects.filter(usuario=obj).update(usuario=None)
            except Exception:
                pass
        if not change:
            role = form.cleaned_data.get("role")
            if role:
                logger.info(f"Asignando grupo: {role} al usuario {obj.username}")
                try:
                    group = Group.objects.get(name=role)
                    obj.groups.add(group)
                    logger.info(f"Grupo {group.name} asignado correctamente")
                except Group.DoesNotExist:
                    logger.error(f"Error: No se encontró el grupo {role}")


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
