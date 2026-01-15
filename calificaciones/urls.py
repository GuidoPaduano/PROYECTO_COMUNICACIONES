from django.urls import path
from . import views

# ⬇️ Nuevo: espejamos endpoints JSON de mensajería SIN prefijo /api
# para que el frontend pueda llamar /mensajes/... directamente.
from .api_mensajes import (
    enviar_mensaje as api_enviar_mensaje,
    enviar_mensaje_grupal as api_enviar_mensaje_grupal,
    mensajes_unread_count,
    mensajes_marcar_todos_leidos,
    mensajes_recibidos as api_mensajes_recibidos,
    responder_mensaje as api_responder_mensaje,
    mensajes_marcar_leido,
    mensajes_conversacion_por_mensaje,
    mensajes_conversacion_por_thread,
)


# ⬇️ Nuevo: espejamos endpoints JSON de notificaciones SIN prefijo /api
from .api_notificaciones import (
    notificaciones_unread_count,
    notificaciones_recientes,
    notificaciones_marcar_leida,
    notificaciones_marcar_todas_leidas,
)

urlpatterns = [
    path("", views.index, name="index"),

    # Notas (HTML)
    path("agregar_nota/", views.agregar_nota, name="agregar_nota"),
    path("ver_notas/", views.ver_notas, name="ver_notas"),
    # Form masivo (HTML legacy; la API JSON está en /api/agregar-nota-masiva/)
    path("agregar_nota_masiva/", views.agregar_nota_masiva, name="agregar_nota_masiva_html"),

    # Mensajería (HTML)
    path("enviar_mensaje/", views.enviar_mensaje, name="enviar_mensaje"),
    path("enviar_comunicado/", views.enviar_comunicado, name="enviar_comunicado"),
    path("ver_mensajes/", views.ver_mensajes, name="ver_mensajes"),

    # Boletín / Historial (HTML)
    path("boletin/<str:alumno_id>/", views.generar_boletin_pdf, name="generar_boletin_pdf"),
    path("historial/profesor/<str:alumno_id>/", views.historial_notas_profesor, name="historial_notas_profesor"),
    path("historial/padre/", views.historial_notas_padre, name="historial_notas_padre"),

    # Asistencia y perfiles (HTML)
    path("pasar_asistencia/", views.pasar_asistencia, name="pasar_asistencia"),
    path("perfil_alumno/<str:alumno_id>/", views.perfil_alumno, name="perfil_alumno"),

    # Calendario (HTML reales, sin stubs)
    path("eventos/", views.calendario_view, name="calendario"),
    path("eventos/crear/", views.crear_evento, name="crear_evento"),
    path("eventos/editar/<int:evento_id>/", views.editar_evento, name="editar_evento"),
    path("eventos/eliminar/<int:evento_id>/", views.eliminar_evento, name="eliminar_evento"),

    # Perfil mínimo (JSON legacy; el nuevo está en /api/perfil_api/)
    path("mi_perfil/", views.mi_perfil, name="mi_perfil"),

    # ─────────────────────────────────────────────────────────────
    # NUEVO: alias JSON sin prefijo para mensajería (compat con frontend)
    # ─────────────────────────────────────────────────────────────

    # Envío individual / grupal
    path("mensajes/enviar/", api_enviar_mensaje, name="api_mensaje_enviar"),
    path("mensajes/enviar", api_enviar_mensaje, name="api_mensaje_enviar_noslash"),
    path("mensajes/enviar_grupal/", api_enviar_mensaje_grupal, name="api_mensaje_enviar_grupal"),
    path("mensajes/enviar_grupal", api_enviar_mensaje_grupal, name="api_mensaje_enviar_grupal_noslash"),

    # Contador no leídos y marcar todos
        # Notificaciones (campanita sistema) - alias sin /api
    path("notificaciones/unread_count/", notificaciones_unread_count, name="notificaciones_unread_count"),
    path("notificaciones/unread_count", notificaciones_unread_count, name="notificaciones_unread_count_noslash"),
    path("notificaciones/recientes/", notificaciones_recientes, name="notificaciones_recientes"),
    path("notificaciones/recientes", notificaciones_recientes, name="notificaciones_recientes_noslash"),
    path("notificaciones/<int:notif_id>/marcar_leida/", notificaciones_marcar_leida, name="notificaciones_marcar_leida"),
    path("notificaciones/<int:notif_id>/marcar_leida", notificaciones_marcar_leida, name="notificaciones_marcar_leida_noslash"),
    path("notificaciones/marcar_todas_leidas/", notificaciones_marcar_todas_leidas, name="notificaciones_marcar_todas_leidas"),
    path("notificaciones/marcar_todas_leidas", notificaciones_marcar_todas_leidas, name="notificaciones_marcar_todas_leidas_noslash"),
    path("mensajes/unread_count/", mensajes_unread_count, name="mensajes_unread_count"),
    path("mensajes/unread_count", mensajes_unread_count, name="mensajes_unread_count_noslash"),
    path("mensajes/marcar_todos_leidos/", mensajes_marcar_todos_leidos, name="mensajes_marcar_todos_leidos"),
    path("mensajes/marcar_todos_leidos", mensajes_marcar_todos_leidos, name="mensajes_marcar_todos_leidos_noslash"),

    # Listados
    path("mensajes/recibidos/", api_mensajes_recibidos, name="mensajes_recibidos"),
    path("mensajes/recibidos", api_mensajes_recibidos, name="mensajes_recibidos_noslash"),
    path("mensajes/listar/", api_mensajes_recibidos, name="mensajes_listar"),
    path("mensajes/listar", api_mensajes_recibidos, name="mensajes_listar_noslash"),

    # Responder
    path("mensajes/responder/", api_responder_mensaje, name="mensajes_responder"),
    path("mensajes/responder", api_responder_mensaje, name="mensajes_responder_noslash"),

    # Marcar leído (uno)
    path("mensajes/<int:mensaje_id>/marcar_leido/", mensajes_marcar_leido, name="mensajes_marcar_leido"),
    path("mensajes/<int:mensaje_id>/marcar_leido", mensajes_marcar_leido, name="mensajes_marcar_leido_noslash"),

    # Conversaciones (hilos)
    path("mensajes/conversacion/<int:mensaje_id>/", mensajes_conversacion_por_mensaje, name="mensajes_conversacion_por_mensaje"),
    path("mensajes/conversacion/<int:mensaje_id>", mensajes_conversacion_por_mensaje, name="mensajes_conversacion_por_mensaje_noslash"),
    path("mensajes/conversacion/thread/<uuid:thread_id>/", mensajes_conversacion_por_thread, name="mensajes_conversacion_por_thread"),
    path("mensajes/conversacion/thread/<uuid:thread_id>", mensajes_conversacion_por_thread, name="mensajes_conversacion_por_thread_noslash"),
]
