# calificaciones/urls_api.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

# SimpleJWT
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
    TokenBlacklistView,
)

# Vistas / APIs ya existentes
from .views import (
    mi_perfil,
    perfil_api,
    auth_logout,

    # catálogos y alumnos
    notas_catalogos,
    alumnos_por_curso,
    alumno_detalle,
    alumno_notas,
)

# ✅ NUEVO: endpoints legacy para /api/notas/...
from .api_notas import (
    notas_listar,
    notas_por_codigo,
)

# APIs de calificaciones (nueva nota, whoami)
from .api_nueva_nota import (
    WhoAmI,
    NuevaNotaDatosIniciales,
    CrearNota,
    CrearNotasMasivo,
)

# APIs de mensajería
from .api_mensajes import (
    enviar_mensaje,
    enviar_mensaje_grupal,
    mensajes_unread_count,
    mensajes_marcar_todos_leidos,
    mensajes_recibidos,
    responder_mensaje,
    mensajes_conversacion_por_mensaje,
    mensajes_conversacion_por_thread,
    mensajes_marcar_leido,
)


# ✅ Extra: eliminar mensajes (bandeja)
from .api_mensajes import mensajes_eliminar

# APIs de notificaciones (campanita sistema)
from .api_notificaciones import (
    notificaciones_unread_count,
    notificaciones_recientes,
    notificaciones_marcar_leida,
    notificaciones_marcar_todas_leidas,
)


# APIs de mensajería (lado alumno)
from .api_mensajes_alumno import (
    docentes_destinatarios,
    alumno_enviar,
)

# APIs de sanciones
from .api_sanciones import (
    sanciones_lista_crear,
    sancion_detalle,
)

# APIs para padres (hijos y sus notas)
from .api_padres import (
    mis_hijos,
    notas_de_hijo,
)

# APIs de eventos para padres (calendario filtrado por hijo/curso)
from .api_eventos_padres import (
    eventos_para_hijo,
    eventos_para_mis_hijos,
)

# ✅ NUEVO: endpoints para calendario (alumno + preceptor selector)
# 🔥 FIX: mi_curso AHORA VIENE DE views.py (lo agregaste ahí)
from .views import mi_curso
from .api_eventos import (
    preceptor_cursos as preceptor_cursos_calendario,  # ✅ selector calendario preceptor
)

# APIs de asistencias / preceptor (+ listado por alumno)
from .api_asistencias import (
    preceptor_cursos as preceptor_cursos_asistencias,  # ✅ alias para evitar choque
    tipos_asistencia,                                  # ✅ NUEVO
    registrar_asistencias,
    asistencias_por_alumno,
    asistencias_por_codigo,
    asistencias_por_curso_y_fecha,
    justificar_asistencia,    editar_detalle_asistencia,
)

# API para crear alumnos (preceptor)
from .api_alumnos import crear_alumno, vincular_mi_legajo, transferir_alumno, cursos_disponibles  # ✅ FIX: importar también vincular

router = DefaultRouter()

# ======================================================
# ✅✅✅ FIX: Compat para front que llama:
#   /api/alumnos/curso/1A/
#   /api/gestion_alumnos/api/curso/1A/
# Pero tu view real espera:
#   /api/alumnos/?curso=1A
# Entonces: wrapper que inyecta curso en querystring y reutiliza alumnos_por_curso.
# ======================================================
def alumnos_por_curso_path(request, curso):
    """
    Wrapper legacy: convierte /alumnos/curso/<curso>/ en /alumnos/?curso=<curso>
    sin tocar el front.
    """
    try:
        django_req = getattr(request, "_request", request)  # DRF Request -> Django HttpRequest
        q = django_req.GET.copy()
        q["curso"] = curso
        django_req.GET = q
    except Exception:
        # Si por algún motivo no se puede mutar GET, igual intentamos seguir.
        pass
    return alumnos_por_curso(request)


urlpatterns = [
    # ===== Auth (JWT) =====
    path("token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("token/verify/", TokenVerifyView.as_view(), name="token_verify"),
    path("token/blacklist/", TokenBlacklistView.as_view(), name="token_blacklist"),

    # ===== Logout de sesión (cookies) =====
    path("auth/logout/", auth_logout, name="auth_logout"),

    # ===== Perfil / WhoAmI =====
    path("auth/whoami/", WhoAmI.as_view(), name="api_whoami"),

    # Rutas “oficiales”
    path("mi-perfil/", mi_perfil, name="mi_perfil_api"),
    path("perfil_api/", perfil_api, name="perfil_api"),

    # Alias compatibilidad (sin prefijo api/ acá adentro)
    path("mi_perfil/", mi_perfil, name="mi_perfil_alias"),
    path("mi_perfil", mi_perfil, name="mi_perfil_alias_noslash"),
    path("perfil/", perfil_api, name="perfil_alias"),
    path("perfil", perfil_api, name="perfil_alias_noslash"),

    # ✅ NUEVO: curso del alumno (para calendario filtrado)
    path("mi-curso/", mi_curso, name="mi_curso"),
    path("mi-curso", mi_curso, name="mi_curso_noslash"),
    path("mi_curso/", mi_curso, name="mi_curso_alias"),
    path("mi_curso", mi_curso, name="mi_curso_alias_noslash"),

    # ===== Catálogos y alumnos =====
    path("notas/catalogos/", notas_catalogos, name="notas_catalogos"),
    path("alumnos/", alumnos_por_curso, name="alumnos_por_curso"),
    path("alumnos", alumnos_por_curso, name="alumnos_por_curso_noslash"),

    # ======================================================
    # ✅✅✅ FIX LEGACY: /api/alumnos/curso/<curso>/
    # ======================================================
    path("alumnos/curso/<str:curso>/", alumnos_por_curso_path, name="alumnos_por_curso_path"),
    path("alumnos/curso/<str:curso>", alumnos_por_curso_path, name="alumnos_por_curso_path_noslash"),

    # ======================================================
    # ✅✅✅ FIX LEGACY EXTRA: /api/gestion_alumnos/api/curso/<curso>/
    # (lo intenta tu front como fallback)
    # ======================================================
    path("gestion_alumnos/api/curso/<str:curso>/", alumnos_por_curso_path, name="gestion_alumnos_curso_path"),
    path("gestion_alumnos/api/curso/<str:curso>", alumnos_por_curso_path, name="gestion_alumnos_curso_path_noslash"),

    # ===== Catalogo de cursos =====
    path("alumnos/cursos/", cursos_disponibles, name="alumnos_cursos"),
    path("alumnos/cursos", cursos_disponibles, name="alumnos_cursos_noslash"),

    # ===== Crear alumno =====
    path("alumnos/crear/", crear_alumno, name="alumnos_crear"),
    path("alumnos/crear", crear_alumno, name="alumnos_crear_noslash"),

    # ✅ FIX: Vincular alumno ↔ usuario por legajo
    path("alumnos/vincular/", vincular_mi_legajo, name="alumnos_vincular"),
    path("alumnos/vincular", vincular_mi_legajo, name="alumnos_vincular_noslash"),
    path("alumnos/transferir/", transferir_alumno, name="alumnos_transferir"),
    path("alumnos/transferir", transferir_alumno, name="alumnos_transferir_noslash"),

    # Dinámicas alumno
    path("alumnos/<str:alumno_id>/", alumno_detalle, name="alumno_detalle"),
    path("alumnos/<str:alumno_id>/notas/", alumno_notas, name="alumno_notas"),
    path("alumnos/<str:alumno_id>/notas", alumno_notas, name="alumno_notas_noslash"),

    # ======================================================
    # ✅✅✅ Compat LEGACY para el front (NOTAS)
    # /api/notas/?id_alumno=00001
    # /api/notas/alumno_codigo/00001/
    # ======================================================
    path("notas/", notas_listar, name="notas_listar"),
    path("notas", notas_listar, name="notas_listar_noslash"),
    path("notas/alumno_codigo/<str:id_alumno>/", notas_por_codigo, name="notas_por_codigo"),
    path("notas/alumno_codigo/<str:id_alumno>", notas_por_codigo, name="notas_por_codigo_noslash"),

    # ===== Nueva Nota (JSON) =====
    path("calificaciones/nueva-nota/datos/", NuevaNotaDatosIniciales.as_view(), name="nueva_nota_datos"),
    path("calificaciones/notas/", CrearNota.as_view(), name="crear_nota"),
    path("calificaciones/notas/masivo/", CrearNotasMasivo.as_view(), name="crear_nota_masivo"),

    # ===== Mensajes =====
    path("mensajes/enviar/", enviar_mensaje, name="api_mensaje_enviar"),
    path("mensajes/enviar", enviar_mensaje, name="api_mensaje_enviar_noslash"),

    path("mensajes/enviar_grupal/", enviar_mensaje_grupal, name="api_mensaje_enviar_grupal"),
    path("mensajes/enviar_grupal", enviar_mensaje_grupal, name="api_mensaje_enviar_grupal_noslash"),

        # Notificaciones (campanita sistema)
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

    path("mensajes/recibidos/", mensajes_recibidos, name="mensajes_recibidos"),
    path("mensajes/recibidos", mensajes_recibidos, name="mensajes_recibidos_noslash"),
    path("mensajes/listar/", mensajes_recibidos, name="mensajes_listar"),
    path("mensajes/listar", mensajes_recibidos, name="mensajes_listar_noslash"),

    path("mensajes/responder/", responder_mensaje, name="mensajes_responder"),
    path("mensajes/responder", responder_mensaje, name="mensajes_responder_noslash"),

    path("mensajes/<int:mensaje_id>/marcar_leido/", mensajes_marcar_leido, name="mensajes_marcar_leido"),
    path("mensajes/<int:mensaje_id>/marcar_leido", mensajes_marcar_leido, name="mensajes_marcar_leido_noslash"),

    
    path("mensajes/<int:mensaje_id>/eliminar/", mensajes_eliminar, name="mensajes_eliminar"),
    path("mensajes/<int:mensaje_id>/eliminar", mensajes_eliminar, name="mensajes_eliminar_noslash"),
path("mensajes/conversacion/<int:mensaje_id>/", mensajes_conversacion_por_mensaje, name="mensajes_conversacion_por_mensaje"),
    path("mensajes/conversacion/<int:mensaje_id>", mensajes_conversacion_por_mensaje, name="mensajes_conversacion_por_mensaje_noslash"),

    path("mensajes/conversacion/thread/<uuid:thread_id>/", mensajes_conversacion_por_thread, name="mensajes_conversacion_por_thread"),
    path("mensajes/conversacion/thread/<uuid:thread_id>", mensajes_conversacion_por_thread, name="mensajes_conversacion_por_thread_noslash"),

    # Mensajería desde perfil de alumno
    path("mensajes/destinatarios_docentes/", docentes_destinatarios, name="docentes_destinatarios"),
    path("mensajes/destinatarios_docentes", docentes_destinatarios, name="docentes_destinatarios_noslash"),

    path("mensajes/alumno/enviar/", alumno_enviar, name="alumno_enviar"),
    path("mensajes/alumno/enviar", alumno_enviar, name="alumno_enviar_noslash"),

    # ===== Padres: hijos y notas =====
    path("padres/mis-hijos/", mis_hijos, name="padres_mis_hijos"),
    path("padres/mis-hijos", mis_hijos, name="padres_mis_hijos_noslash"),

    path("padres/hijos/<str:alumno_id>/notas/", notas_de_hijo, name="padres_notas_hijo"),
    path("padres/hijos/<str:alumno_id>/notas", notas_de_hijo, name="padres_notas_hijo_noslash"),

    # Padres — eventos filtrados por hijo/curso
    path("padres/hijos/<str:alumno_id>/eventos/", eventos_para_hijo, name="padre_eventos_hijo"),
    path("padres/hijos/<str:alumno_id>/eventos", eventos_para_hijo, name="padre_eventos_hijo_noslash"),

    path("padres/mis-hijos/eventos/", eventos_para_mis_hijos, name="padre_eventos_todos"),
    path("padres/mis-hijos/eventos", eventos_para_mis_hijos, name="padre_eventos_todos_noslash"),

    # ===== Preceptores — cursos (CALENDARIO) =====
    path("preceptor/cursos/", preceptor_cursos_calendario, name="preceptor_cursos_calendario"),
    path("preceptor/cursos", preceptor_cursos_calendario, name="preceptor_cursos_calendario_noslash"),

    # ===== Preceptores — cursos (ASISTENCIAS) =====
    path("preceptor/asistencias/cursos/", preceptor_cursos_asistencias, name="preceptor_cursos_asistencias"),
    path("preceptor/asistencias/cursos", preceptor_cursos_asistencias, name="preceptor_cursos_asistencias_noslash"),

    # FIX COMPAT
    path("preceptores/mis-cursos/", preceptor_cursos_asistencias, name="preceptores_mis_cursos"),
    path("preceptores/mis-cursos", preceptor_cursos_asistencias, name="preceptores_mis_cursos_noslash"),
    path("cursos/mis-cursos/", preceptor_cursos_asistencias, name="cursos_mis_cursos"),
    path("cursos/mis-cursos", preceptor_cursos_asistencias, name="cursos_mis_cursos_noslash"),

    # ===== Asistencias =====
    path("asistencias/tipos/", tipos_asistencia, name="asistencias_tipos"),
    path("asistencias/tipos", tipos_asistencia, name="asistencias_tipos_noslash"),

    path("asistencias/registrar/", registrar_asistencias, name="asistencias_registrar"),
    path("asistencias/registrar", registrar_asistencias, name="asistencias_registrar_noslash"),

    path("asistencias/<int:pk>/justificar/", justificar_asistencia, name="asistencias_justificar"),
    path("asistencias/<int:pk>/justificar", justificar_asistencia, name="asistencias_justificar_noslash"),

    # ✅ Legacy extra: algunos frontends viejos llaman /asistencias/justificar/<id>/
    # (mismo handler)
    path("asistencias/justificar/<int:pk>/", justificar_asistencia, name="asistencias_justificar_legacy"),
    path("asistencias/justificar/<int:pk>", justificar_asistencia, name="asistencias_justificar_legacy_noslash"),

    # ✅ Más compat (singular / nombres alternativos)
    path("asistencia/<int:pk>/justificar/", justificar_asistencia, name="asistencia_justificar"),
    path("asistencia/<int:pk>/justificar", justificar_asistencia, name="asistencia_justificar_noslash"),

    path("asistencia/justificar/<int:pk>/", justificar_asistencia, name="asistencia_justificar_legacy"),
    path("asistencia/justificar/<int:pk>", justificar_asistencia, name="asistencia_justificar_legacy_noslash"),

    path("asistencias/<int:pk>/toggle_justificada/", justificar_asistencia, name="asistencias_toggle_justificada"),
    path("asistencias/<int:pk>/toggle_justificada", justificar_asistencia, name="asistencias_toggle_justificada_noslash"),

    # ===== Detalle / Observación (solo preceptor/admin) =====
    path("asistencias/<int:pk>/detalle/", editar_detalle_asistencia, name="asistencias_detalle"),
    path("asistencias/<int:pk>/detalle", editar_detalle_asistencia, name="asistencias_detalle_noslash"),
    path("asistencias/<int:pk>/observacion/", editar_detalle_asistencia, name="asistencias_observacion"),
    path("asistencias/<int:pk>/observacion", editar_detalle_asistencia, name="asistencias_observacion_noslash"),

    # Compat legacy (orden invertido)
    path("asistencias/detalle/<int:pk>/", editar_detalle_asistencia, name="asistencias_detalle_legacy"),
    path("asistencias/detalle/<int:pk>", editar_detalle_asistencia, name="asistencias_detalle_legacy_noslash"),
    path("asistencias/observacion/<int:pk>/", editar_detalle_asistencia, name="asistencias_observacion_legacy"),
    path("asistencias/observacion/<int:pk>", editar_detalle_asistencia, name="asistencias_observacion_legacy_noslash"),

    # Compat singular
    path("asistencia/<int:pk>/detalle/", editar_detalle_asistencia, name="asistencia_detalle"),
    path("asistencia/<int:pk>/detalle", editar_detalle_asistencia, name="asistencia_detalle_noslash"),
    path("asistencia/detalle/<int:pk>/", editar_detalle_asistencia, name="asistencia_detalle_legacy"),
    path("asistencia/detalle/<int:pk>", editar_detalle_asistencia, name="asistencia_detalle_legacy_noslash"),



    path("asistencias/", asistencias_por_alumno, name="asistencias_listar"),
    path("asistencias", asistencias_por_alumno, name="asistencias_listar_noslash"),
    path("asistencias/alumno/<int:alumno_id>/", asistencias_por_alumno, name="asistencias_por_alumno"),
    path("asistencias/alumno/<int:alumno_id>", asistencias_por_alumno, name="asistencias_por_alumno_noslash"),

    path("asistencias/alumno_codigo/<str:id_alumno>/", asistencias_por_codigo, name="asistencias_por_codigo"),
    path("asistencias/alumno_codigo/<str:id_alumno>", asistencias_por_codigo, name="asistencias_por_codigo_noslash"),

    path("asistencias/curso/", asistencias_por_curso_y_fecha, name="asistencias_por_curso_y_fecha"),
    path("asistencias/curso", asistencias_por_curso_y_fecha, name="asistencias_por_curso_y_fecha_noslash"),

    # ===== Eventos (CRUD + tipos) =====
    path("", include("calificaciones.eventos_urls")),

    # ===== Sanciones =====
    path("sanciones/", sanciones_lista_crear, name="sanciones_lista_crear"),
    path("sanciones/<int:pk>/", sancion_detalle, name="sancion_detalle"),

    # DRF router
    path("", include(router.urls)),
]