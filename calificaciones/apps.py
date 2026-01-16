from django.apps import AppConfig


class CalificacionesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'calificaciones'

    def ready(self):
        # Aseguramos cargar el módulo con el modelo relacional de preceptores
        # (no falla si el archivo no declara nada ejecutable).
        from . import models_preceptores  # noqa: F401

        # Registro en admin se maneja desde calificaciones/admin.py
