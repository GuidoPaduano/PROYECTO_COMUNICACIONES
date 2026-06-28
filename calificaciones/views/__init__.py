# calificaciones/views/__init__.py
# Paquete views — re-exporta todos los símbolos públicos que antes vivían en views.py.
# urls.py, urls_api.py y api_nueva_nota.py importan desde aquí sin cambios.

# ── Notificaciones (usado por api_nueva_nota.py) ──────────────────────────────
from ._acceso import _get_preview_role  # noqa: F401

# ── Vistas de acceso / formularios / helpers (internos, usados por otros módulos) ──
# (No se re-exportan símbolos privados a menos que sean necesarios externamente)

# ── Perfil ────────────────────────────────────────────────────────────────────
from ._perfil import index, perfil_api  # noqa: F401

# ── Cursos / catálogos ────────────────────────────────────────────────────────
from ._cursos import (  # noqa: F401
    mi_curso,
    notas_catalogos,
    alumnos_por_curso,
    alumnos_por_curso_path,
)

# ── Alumnos ───────────────────────────────────────────────────────────────────
from ._alumnos import alumno_detalle, alumno_notas  # noqa: F401

# ── Notas HTML ────────────────────────────────────────────────────────────────
from ._notas_html import agregar_nota, agregar_nota_masiva, ver_notas  # noqa: F401

# ── Mensajes HTML ─────────────────────────────────────────────────────────────
from ._mensajes_html import enviar_mensaje, enviar_comunicado, ver_mensajes  # noqa: F401

# ── Boletín / Historial ───────────────────────────────────────────────────────
from ._boletin import (  # noqa: F401
    generar_boletin_pdf,
    historial_notas_profesor,
    historial_notas_padre,
)

# ── Calendario ────────────────────────────────────────────────────────────────
from ._calendario import (  # noqa: F401
    calendario_view,
    crear_evento,
    editar_evento,
    eliminar_evento,
)

# ── Asistencias / Perfiles ────────────────────────────────────────────────────
from ._asistencia_html import pasar_asistencia, perfil_alumno  # noqa: F401

# ── Auth ──────────────────────────────────────────────────────────────────────
from ._auth import (  # noqa: F401
    mi_perfil,
    auth_logout,
    auth_change_password,
    mensajes_unread_count,
)
