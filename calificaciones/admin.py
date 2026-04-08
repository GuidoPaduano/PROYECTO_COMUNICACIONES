import logging
from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User, Group
from django.utils.html import format_html

from .forms import SchoolAdminForm
from .forms_user import CustomUserCreationForm, CustomUserChangeForm
from .models import (
    School,
    SchoolCourse,
    Alumno,
    Nota,
    Sancion,
    Asistencia,
    AlertaAcademica,
    AlertaInasistencia,
)
from .models_preceptores import PreceptorCurso, ProfesorCurso
from .schools import (
    DEFAULT_SCHOOL_ACCENT_COLOR,
    DEFAULT_SCHOOL_PRIMARY_COLOR,
    school_to_dict,
)

logger = logging.getLogger(__name__)


def _related_school_course(obj):
    school_course = getattr(obj, "school_course", None)
    if school_course is not None:
        return school_course
    alumno = getattr(obj, "alumno", None)
    return getattr(alumno, "school_course", None) if alumno is not None else None


def _related_course_code(obj) -> str:
    school_course = _related_school_course(obj)
    if school_course is not None:
        return getattr(school_course, "code", "") or ""
    alumno = getattr(obj, "alumno", None)
    if alumno is not None:
        return getattr(alumno, "curso", "") or ""
    return getattr(obj, "curso", "") or ""


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    form = SchoolAdminForm
    list_display = ("name", "short_name", "slug", "branding_palette", "logo_preview_small", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "short_name", "slug", "logo_url")
    ordering = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("branding_palette_preview", "logo_preview")
    fieldsets = (
        (None, {"fields": ("name", "short_name", "slug", "is_active")}),
        (
            "Branding",
            {
                "fields": ("logo_url", "logo_preview", "primary_color", "accent_color", "branding_palette_preview"),
                "description": "Configuracion visual usada por login, sidebar y encabezados.",
            },
        ),
    )

    @admin.display(description="Colores")
    def branding_palette(self, obj):
        data = school_to_dict(obj) or {}
        primary = data.get("primary_color", DEFAULT_SCHOOL_PRIMARY_COLOR)
        accent = data.get("accent_color", DEFAULT_SCHOOL_ACCENT_COLOR)
        return format_html(
            '<div style="display:flex; gap:6px; align-items:center;">'
            '<span style="display:inline-block; width:14px; height:14px; border-radius:999px; border:1px solid #d1d5db; background:{};"></span>'
            '<span style="font-family:monospace;">{}</span>'
            '<span style="display:inline-block; width:14px; height:14px; border-radius:999px; border:1px solid #d1d5db; background:{}; margin-left:8px;"></span>'
            '<span style="font-family:monospace;">{}</span>'
            "</div>",
            primary,
            primary,
            accent,
            accent,
        )

    @admin.display(description="Logo")
    def logo_preview_small(self, obj):
        data = school_to_dict(obj) or {}
        logo_url = data.get("logo_url", "")
        school_name = data.get("name", "Colegio")
        return format_html(
            '<img src="{}" alt="{}" style="width:32px; height:32px; object-fit:contain; border-radius:8px; background:#fff; border:1px solid #e5e7eb; padding:4px;" />',
            logo_url,
            school_name,
        )

    @admin.display(description="Vista previa de colores")
    def branding_palette_preview(self, obj):
        return self.branding_palette(obj)

    @admin.display(description="Vista previa del logo")
    def logo_preview(self, obj):
        data = school_to_dict(obj) or {}
        logo_url = data.get("logo_url", "")
        school_name = data.get("name", "Colegio")
        return format_html(
            '<div style="display:flex; align-items:center; gap:12px;">'
            '<img src="{}" alt="{}" style="width:72px; height:72px; object-fit:contain; border-radius:16px; background:#fff; border:1px solid #e5e7eb; padding:10px;" />'
            '<div><strong>{}</strong><br/><span style="color:#6b7280;">{}</span></div>'
            "</div>",
            logo_url,
            school_name,
            data.get("short_name") or school_name,
            logo_url,
        )


@admin.register(SchoolCourse)
class SchoolCourseAdmin(admin.ModelAdmin):
    list_display = ("school", "code", "name", "is_active", "sort_order")
    list_filter = ("school", "is_active")
    search_fields = ("school__name", "code", "name")
    ordering = ("school", "sort_order", "code")

# ─────────────────────────────────────────────────────────────
# Alumno
# ─────────────────────────────────────────────────────────────
@admin.register(Alumno)
class AlumnoAdmin(admin.ModelAdmin):
    list_display = ("school", "school_course", "curso", "apellido", "nombre", "id_alumno", "padre")
    list_filter = ("school", "school_course")
    search_fields = ("nombre", "apellido", "id_alumno", "school__name", "school_course__code", "school_course__name")
    ordering = ("school__name", "school_course__sort_order", "school_course__code", "apellido", "nombre")
    list_select_related = ("school", "school_course", "padre")


# ─────────────────────────────────────────────────────────────
# Nota
# ─────────────────────────────────────────────────────────────
@admin.register(Nota)
class NotaAdmin(admin.ModelAdmin):
    list_display = ("school", "alumno", "school_course_del_alumno", "curso_del_alumno", "materia", "tipo", "calificacion", "cuatrimestre", "fecha")
    list_filter = ("school", "alumno__school_course", "materia", "tipo", "cuatrimestre", "fecha")
    search_fields = ("school__name", "alumno__nombre", "alumno__apellido", "alumno__id_alumno", "alumno__school_course__code", "alumno__school_course__name", "observaciones")
    ordering = ("-fecha", "-id")
    date_hierarchy = "fecha"
    list_select_related = ("school", "alumno", "alumno__school_course")
    autocomplete_fields = ("alumno",)

    @admin.display(description="Curso colegio", ordering="alumno__school_course__sort_order")
    def school_course_del_alumno(self, obj):
        return _related_school_course(obj)

    @admin.display(description="Curso", ordering="alumno__school_course__code")
    def curso_del_alumno(self, obj):
        return _related_course_code(obj)


# ─────────────────────────────────────────────────────────────
# Sanción (FIX: el admin estaba apuntando a campos que NO existen)
# ─────────────────────────────────────────────────────────────
@admin.register(Sancion)
class SancionAdmin(admin.ModelAdmin):
    list_display = ("school", "alumno", "school_course_del_alumno", "curso_del_alumno", "tipo", "fecha", "docente")
    list_filter = ("school", "alumno__school_course", "tipo", "fecha")
    search_fields = (
        "school__name",
        "motivo",
        "detalle",
        "docente",
        "alumno__nombre",
        "alumno__apellido",
        "alumno__id_alumno",
        "alumno__school_course__code",
        "alumno__school_course__name",
    )
    ordering = ("-fecha", "-id")
    date_hierarchy = "fecha"
    list_select_related = ("school", "alumno", "alumno__school_course")
    autocomplete_fields = ("alumno",)

    @admin.display(description="Curso colegio", ordering="alumno__school_course__sort_order")
    def school_course_del_alumno(self, obj):
        return _related_school_course(obj)

    @admin.display(description="Curso", ordering="alumno__school_course__code")
    def curso_del_alumno(self, obj):
        return _related_course_code(obj)


# ─────────────────────────────────────────────────────────────
# Asistencia (nuevo modelo con tipo_asistencia)
# ─────────────────────────────────────────────────────────────
@admin.register(Asistencia)
class AsistenciaAdmin(admin.ModelAdmin):
    list_display = ("school", "alumno", "school_course_del_alumno", "curso_del_alumno", "fecha", "tipo_asistencia", "presente", "tarde", "creado_por")
    list_filter = ("school", "alumno__school_course", "tipo_asistencia", "fecha", "presente", "tarde")
    search_fields = (
        "school__name",
        "alumno__nombre",
        "alumno__apellido",
        "alumno__id_alumno",
        "alumno__school_course__code",
        "alumno__school_course__name",
        "observacion",
    )
    ordering = ("-fecha", "-id")
    date_hierarchy = "fecha"
    list_select_related = ("school", "alumno", "alumno__school_course", "creado_por")
    autocomplete_fields = ("alumno",)

    @admin.display(description="Curso colegio", ordering="alumno__school_course__sort_order")
    def school_course_del_alumno(self, obj):
        return _related_school_course(obj)

    @admin.display(description="Curso", ordering="alumno__school_course__code")
    def curso_del_alumno(self, obj):
        return _related_course_code(obj)


@admin.register(AlertaAcademica)
class AlertaAcademicaAdmin(admin.ModelAdmin):
    list_display = ("school", "alumno", "school_course_del_alumno", "materia", "cuatrimestre", "severidad", "riesgo_ponderado", "estado", "fecha_evento", "creada_en")
    list_filter = ("school", "severidad", "estado", "materia", "cuatrimestre", "alumno__school_course")
    search_fields = ("school__name", "alumno__nombre", "alumno__apellido", "alumno__id_alumno", "alumno__school_course__code", "alumno__school_course__name", "materia")
    ordering = ("-creada_en", "-id")
    date_hierarchy = "creada_en"
    list_select_related = ("school", "alumno", "alumno__school_course", "creada_por", "nota_disparadora")
    autocomplete_fields = ("alumno", "creada_por", "nota_disparadora")

    @admin.display(description="Curso colegio", ordering="alumno__school_course__sort_order")
    def school_course_del_alumno(self, obj):
        return _related_school_course(obj)


@admin.register(AlertaInasistencia)
class AlertaInasistenciaAdmin(admin.ModelAdmin):
    list_display = ("alumno", "school_course", "curso", "tipo_asistencia", "motivo", "valor_actual", "umbral", "estado", "fecha_evento", "creada_en")
    list_filter = ("school", "estado", "motivo", "tipo_asistencia", "school_course")
    search_fields = ("alumno__nombre", "alumno__apellido", "alumno__id_alumno", "curso", "school_course__code", "school_course__name")
    ordering = ("-creada_en", "-id")
    date_hierarchy = "creada_en"
    list_select_related = ("school", "alumno", "school_course", "creada_por", "asistencia_disparadora")
    autocomplete_fields = ("school", "alumno", "school_course", "creada_por", "asistencia_disparadora")


# ====================================================================================
# Preceptor / Profesor: asignaciones de cursos (filtrar usuarios por grupo)
# ====================================================================================
@admin.register(PreceptorCurso)
class PreceptorCursoAdmin(admin.ModelAdmin):
    list_display = ("school", "preceptor", "school_course", "curso", "asignado_en")
    list_filter = ("school", "school_course")
    search_fields = (
        "school__name",
        "school_course__code",
        "school_course__name",
        "preceptor__username",
        "preceptor__first_name",
        "preceptor__last_name",
    )
    ordering = ("school__name", "school_course__sort_order", "school_course__code", "preceptor__username", "id")
    list_select_related = ("school", "school_course", "preceptor")
    autocomplete_fields = ("school", "school_course", "preceptor")

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
    list_display = ("school", "profesor", "school_course", "curso", "asignado_en")
    list_filter = ("school", "school_course")
    search_fields = (
        "school__name",
        "school_course__code",
        "school_course__name",
        "profesor__username",
        "profesor__first_name",
        "profesor__last_name",
    )
    ordering = ("school__name", "school_course__sort_order", "school_course__code", "profesor__username", "id")
    list_select_related = ("school", "school_course", "profesor")
    autocomplete_fields = ("school", "school_course", "profesor")

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
        ("Vinculacion", {"fields": ("school", "curso", "alumno")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "email", "password1", "password2", "role"),
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        base_form = super().get_form(request, obj, **kwargs)

        class RequestAwareForm(base_form):
            def __init__(self, *args, **inner_kwargs):
                inner_kwargs["request"] = request
                super().__init__(*args, **inner_kwargs)

        RequestAwareForm.__name__ = base_form.__name__
        return RequestAwareForm

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
