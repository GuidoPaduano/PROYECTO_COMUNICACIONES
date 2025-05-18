import logging
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User, Group
from .forms import CustomUserCreationForm
from .models import Alumno, Nota

logger = logging.getLogger(__name__)

# Personalizar el admin de Alumno
@admin.register(Alumno)
class AlumnoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'id_alumno', 'curso', 'padre')  # Campos visibles en la lista
    list_filter = ('curso',)  # Filtro por curso en la barra lateral
    search_fields = ('nombre', 'id_alumno')  # Buscar por nombre o ID
    ordering = ('curso', 'nombre')  # Ordenar por curso y luego por nombre

# Personalizar el admin de User
class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2', 'role'),
        }),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            role = form.cleaned_data.get('role')
            if role:
                logger.info(f"Asignando grupo: {role} al usuario {obj.username}")
                try:
                    group = Group.objects.get(name=role)
                    obj.groups.add(group)
                    logger.info(f"Grupo {group.name} asignado correctamente")
                except Group.DoesNotExist:
                    logger.error(f"Error: No se encontró el grupo {role}")

# Registrar modelos
admin.site.register(Nota, admin.ModelAdmin)
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
