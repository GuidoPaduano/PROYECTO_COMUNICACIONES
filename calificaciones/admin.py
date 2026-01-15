import logging
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User, Group

from .forms_user import CustomUserCreationForm
from .models import (
    Alumno,
    Nota,
    Sancion,
    Asistencia,
)

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


# ─────────────────────────────────────────────────────────────
# User
# ─────────────────────────────────────────────────────────────
class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "email", "password1", "password2", "role"),
        }),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
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
