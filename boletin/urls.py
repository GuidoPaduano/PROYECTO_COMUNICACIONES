# boletin/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),

    # APIs
    path("api/", include("calificaciones.urls_api")),   # acá ya está auth/whoami

    # Vistas HTML del sitio
    path("", include("calificaciones.urls")),
    path("", include("calificaciones.urls_redir")),

    # Auth de Django (login/logout/reset)
    path("accounts/", include("django.contrib.auth.urls")),
]
