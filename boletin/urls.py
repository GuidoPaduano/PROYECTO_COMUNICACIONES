# boletin/urls.py
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve as serve_media

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

urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", serve_media, {"document_root": settings.MEDIA_ROOT}),
]
