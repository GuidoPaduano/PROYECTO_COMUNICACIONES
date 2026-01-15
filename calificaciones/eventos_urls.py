# calificaciones/eventos_urls.py
from django.urls import path
from .api_eventos import (
    # ✅ REST real (FRONT actual)
    eventos_collection,
    eventos_detalle,

    # ✅ Rutas existentes (compatibilidad)
    eventos_crear,
    eventos_editar,
    eventos_eliminar,
    eventos_tipos,
)

urlpatterns = [
    # -----------------------------
    # ✅ FRONT actual (REST-like real)
    # -----------------------------
    # GET  /eventos/        -> listar
    # POST /eventos/        -> crear
    path("eventos/", eventos_collection, name="eventos_collection"),
    path("eventos", eventos_collection, name="eventos_collection_noslash"),

    # PATCH/PUT/POST /eventos/<pk>/ -> editar
    # DELETE         /eventos/<pk>/ -> eliminar
    path("eventos/<int:pk>/", eventos_detalle, name="eventos_detalle"),
    path("eventos/<int:pk>", eventos_detalle, name="eventos_detalle_noslash"),

    # -----------------------------
    # ✅ Rutas viejas (se mantienen)
    # -----------------------------
    path("eventos/crear/", eventos_crear, name="eventos_crear"),
    path("eventos/crear", eventos_crear, name="eventos_crear_noslash"),

    path("eventos/editar/<int:pk>/", eventos_editar, name="eventos_editar"),
    path("eventos/editar/<int:pk>", eventos_editar, name="eventos_editar_noslash"),

    path("eventos/eliminar/<int:pk>/", eventos_eliminar, name="eventos_eliminar"),
    path("eventos/eliminar/<int:pk>", eventos_eliminar, name="eventos_eliminar_noslash"),

    path("eventos/tipos/", eventos_tipos, name="eventos_tipos"),
    path("eventos/tipos", eventos_tipos, name="eventos_tipos_noslash"),
]
