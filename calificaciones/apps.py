from django.apps import AppConfig


class CalificacionesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'calificaciones'

    def ready(self):
        # Aseguramos cargar el módulo con el modelo relacional de preceptores
        # (no falla si el archivo no declara nada ejecutable).
        from . import models_preceptores  # noqa: F401

        # Registramos el modelo en el admin sin romper si ya está registrado
        try:
            from django.contrib import admin
            from django.contrib.admin.sites import AlreadyRegistered
            from .models_preceptores import PreceptorCurso

            admin.site.register(PreceptorCurso)
        except AlreadyRegistered:
            pass
        except Exception:
            # Evita romper el arranque en contextos donde el admin no está disponible (tests, scripts)
            pass
