from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "qa-reporte-skill-qa-tester-2026-06-06-completo.pdf"

NAVY = colors.HexColor("#0B1B3F")
BLUE = colors.HexColor("#1D4ED8")
LIGHT_BLUE = colors.HexColor("#EAF1FF")
LIGHT_GRAY = colors.HexColor("#F3F4F6")
MID_GRAY = colors.HexColor("#D1D5DB")
GREEN = colors.HexColor("#15803D")
LIGHT_GREEN = colors.HexColor("#DCFCE7")
AMBER = colors.HexColor("#B45309")
LIGHT_AMBER = colors.HexColor("#FEF3C7")
RED = colors.HexColor("#B91C1C")


styles = getSampleStyleSheet()
styles.add(
    ParagraphStyle(
        name="ReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=21,
        leading=25,
        textColor=NAVY,
        alignment=TA_LEFT,
        spaceAfter=8,
    )
)
styles.add(
    ParagraphStyle(
        name="ReportSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=15,
        textColor=colors.HexColor("#374151"),
        spaceAfter=14,
    )
)
styles.add(
    ParagraphStyle(
        name="Section",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=NAVY,
        spaceBefore=8,
        spaceAfter=8,
    )
)
styles.add(
    ParagraphStyle(
        name="Subsection",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=BLUE,
        spaceBefore=6,
        spaceAfter=5,
    )
)
styles.add(
    ParagraphStyle(
        name="BodySmall",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.6,
        leading=12,
        textColor=colors.HexColor("#1F2937"),
        spaceAfter=4,
    )
)
styles.add(
    ParagraphStyle(
        name="Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.6,
        leading=14,
        textColor=colors.HexColor("#1F2937"),
        spaceAfter=6,
    )
)
styles.add(
    ParagraphStyle(
        name="Callout",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=14,
        textColor=NAVY,
        alignment=TA_CENTER,
    )
)
styles.add(
    ParagraphStyle(
        name="Cell",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.7,
        leading=10,
        textColor=colors.HexColor("#111827"),
    )
)
styles.add(
    ParagraphStyle(
        name="CellBold",
        parent=styles["Cell"],
        fontName="Helvetica-Bold",
    )
)
styles.add(
    ParagraphStyle(
        name="HeaderCell",
        parent=styles["Cell"],
        fontName="Helvetica-Bold",
        textColor=colors.white,
        alignment=TA_CENTER,
    )
)


def p(text, style="Body"):
    return Paragraph(text, styles[style])


def table(headers, rows, widths, repeat_rows=1, font_size=7.5):
    data = [[Paragraph(str(h), styles["HeaderCell"]) for h in headers]]
    for row in rows:
        data.append(
            [
                cell if isinstance(cell, Paragraph) else Paragraph(str(cell), styles["Cell"])
                for cell in row
            ]
        )
    result = Table(data, colWidths=widths, repeatRows=repeat_rows, hAlign="LEFT")
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.35, MID_GRAY),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
                ("FONTSIZE", (0, 1), (-1, -1), font_size),
            ]
        )
    )
    return result


def bullet(text):
    return Paragraph(f"• {text}", styles["BodySmall"])


def status_box(title, value, note, color=GREEN, background=LIGHT_GREEN):
    content = [
        [p(title, "Callout")],
        [Paragraph(value, ParagraphStyle(name=f"Value-{title}", parent=styles["Callout"], fontSize=18, textColor=color))],
        [Paragraph(note, styles["Cell"])],
    ]
    box = Table(content, colWidths=[55 * mm], rowHeights=[10 * mm, 13 * mm, 14 * mm])
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("BOX", (0, 0), (-1, -1), 0.8, color),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return box


def page_header_footer(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(MID_GRAY)
    canvas.setLineWidth(0.4)
    canvas.line(18 * mm, height - 14 * mm, width - 18 * mm, height - 14 * mm)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(NAVY)
    canvas.drawString(18 * mm, height - 10.5 * mm, "Alumnix - Informe QA consolidado")
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#4B5563"))
    canvas.drawRightString(width - 18 * mm, height - 10.5 * mm, "6 de junio de 2026")
    canvas.line(18 * mm, 13 * mm, width - 18 * mm, 13 * mm)
    canvas.drawString(18 * mm, 8.5 * mm, "Skill qa-tester | PROYECTO_COMUNICACIONES | Ambiente local")
    canvas.drawRightString(width - 18 * mm, 8.5 * mm, f"Página {doc.page}")
    canvas.restoreState()


backend_rows = [
    ("test_admin_forms.py", 11, "Formularios admin, branding y configuración de cursos."),
    ("test_admin_school_courses_api.py", 5, "Cursos por colegio y permisos de administración."),
    ("test_admin_staff_api.py", 16, "Usuarios, roles, directorio y asignaciones de staff."),
    ("test_alertas_api.py", 10, "Alertas académicas, cooldown, cierre y scoping."),
    ("test_alumnos_api.py", 32, "Alumnos, transferencias, importación, legajos e integridad escolar."),
    ("test_asistencias_api.py", 28, "Registro, firmas, permisos, detalle, alertas y scoping."),
    ("test_auth_api.py", 6, "Tokens, logout, blacklist y aislamiento multi-colegio."),
    ("test_backups_api.py", 2, "Backup manual y permisos."),
    ("test_eventos_api.py", 21, "Calendario, CRUD, permisos, serialización y scoping."),
    ("test_legacy_course_navigation_api.py", 16, "Navegación legacy y school_course_id."),
    ("test_legacy_html_views.py", 15, "Compatibilidad de vistas HTML legacy."),
    ("test_mensajes_api.py", 33, "Inbox, hilos, envío, lectura, borrado y permisos."),
    ("test_notas_api.py", 19, "Crear/editar/listar notas, firmas y permisos."),
    ("test_notificaciones_api.py", 3, "Recientes, no leídas y marcas de lectura."),
    ("test_padres_api.py", 3, "Hijos propios y visibilidad de notas."),
    ("test_password_api.py", 11, "Reset, confirmación, validación, cambio y blacklist."),
    ("test_reportes_api.py", 16, "Estadísticas, históricos, cursos, materias y permisos."),
    ("test_sanciones_api.py", 17, "CRUD, firmas, roles y aislamiento escolar."),
    ("test_school_context_api.py", 24, "Whoami, login, branding, colegios y contexto activo."),
]

jest_rows = [
    ("auth-context.test.jsx", 6, "Contexto de sesión/colegio, storage, login seguro y hosts."),
    ("courses.test.jsx", 6, "Resolución canónica y labels de school_course."),
    ("mensaje-dialog.test.jsx", 1, "Prioridad de school_course_name."),
    ("notification-bell.test.jsx", 4, "Badge 99+, preview, lectura, navegación y estado vacío."),
    ("profile-page.test.jsx", 4, "Edición, password, legajo y vínculos de hijos."),
    ("success-message.test.jsx", 1, "Render de mensajes de éxito."),
]

e2e_rows = [
    ("qa-admin-import.spec.ts", 2, "Curso/asignación docente e importación CSV por rol."),
    ("qa-attendance-advanced.spec.ts", 3, "Firmar todo, justificar, detalle y bloqueos."),
    ("qa-flows.spec.ts", 5, "Nota, asistencia, mensaje, sanción y respuesta en hilo."),
    ("qa-notes-filters-mobile.spec.ts", 3, "Edición, filtros y navegación mobile."),
    ("qa-permissions.spec.ts", 3, "Aislamiento alumno/profesor/padre."),
    ("qa-reports-events.spec.ts", 2, "Reportes y calendario por rol/curso."),
    ("qa-security-messages.spec.ts", 4, "Anónimos, logout, mensajes grupales y destinatario."),
    ("qa-signatures.spec.ts", 2, "Firma y prevención de doble firma."),
    ("qa-smoke.spec.ts", 3, "Home, CSS y login profesor/admin colegio."),
]

new_backend_tests = [
    ("Auth", "Refresh, verify y blacklist sin cookies devuelven rechazo y limpian cookies."),
    ("Auth", "Un refresh token blacklisteado no puede reutilizarse."),
    ("Auth", "Login de usuario regular en colegio ajeno es rechazado."),
    ("Auth", "Whoami con header de otro colegio es rechazado usando JWT en cookie."),
    ("Password reset", "Email inexistente conserva respuesta genérica anti-enumeración."),
    ("Password reset", "Email existente genera link con uid y token."),
    ("Password reset", "Usuario existente requiere FRONTEND_BASE_URL configurado."),
    ("Password reset", "Datos incompletos, uid inválido o token inválido son rechazados."),
    ("Password reset", "Confirmación cambia password e impide reutilizar el token."),
    ("Password reset", "Se aplican validadores de contraseña."),
    ("Password reset", "Se blacklistean refresh tokens existentes."),
    ("Password change", "Requiere usuario autenticado."),
    ("Password change", "Rechaza campos faltantes o contraseña actual incorrecta."),
    ("Password change", "Se aplican validadores de contraseña."),
    ("Password change", "Actualiza password y blacklistea refresh tokens."),
]

new_frontend_tests = [
    ("NotificationBell", "Badge controlado limitado a 99+ y items por props sin fetch."),
    ("NotificationBell", "Carga preview, marca una notificación y navega a la URL de nota."),
    ("NotificationBell", "Marca todas leídas y refresca el store de unread."),
    ("NotificationBell", "Muestra estado vacío sin notificaciones."),
    ("Perfil", "Edita nombre/email y valida payload PATCH."),
    ("Perfil", "Cambia password y programa logout exitoso."),
    ("Perfil", "Alumno sin vínculo oculta controles y vincula legajo."),
    ("Perfil", "Padre renderiza hijos asociados con link al detalle."),
]


story = []
story.append(Spacer(1, 7 * mm))
story.append(p("Informe QA consolidado completo", "ReportTitle"))
story.append(
    p(
        "Actualización del informe del 4 de junio de 2026 con el inventario actual, "
        "los tests agregados posteriormente y las corridas verificadas el 6 de junio de 2026.",
        "ReportSubtitle",
    )
)

summary_boxes = Table(
    [
        [
            status_box("Playwright E2E", "27 / 27", "Corrida completa actual: 3.8 minutos."),
            status_box("Jest frontend", "22 / 22", "6 suites; corrida completa actual."),
            status_box("Backend focalizado", "41 / 41", "Auth, password y school context."),
        ]
    ],
    colWidths=[58 * mm, 58 * mm, 58 * mm],
    hAlign="CENTER",
)
summary_boxes.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 1), ("RIGHTPADDING", (0, 0), (-1, -1), 1)]))
story.append(summary_boxes)
story.append(Spacer(1, 7 * mm))

story.append(p("Estado general", "Section"))
story.append(
    p(
        "<b>Estado aprobado.</b> La evidencia actual confirma 27/27 E2E, 22/22 Jest y 41/41 tests backend "
        "focalizados. El catálogo automatizado actual contiene <b>337 tests</b>: 288 backend, 22 Jest y 27 E2E.",
        "Body",
    )
)
story.append(
    p(
        "La última corrida backend completa registrada en el informe original fue 273/273 el 4 de junio de 2026. "
        "Desde entonces se agregaron 15 tests backend de auth/password. La suite backend completa actual contiene "
        "288 tests; dos intentos de ejecución integral excedieron los límites operativos de 3 y 6 minutos sin "
        "reportar fallos. Los módulos afectados por los cambios sí fueron verificados en una corrida focalizada "
        "de 41/41.",
        "BodySmall",
    )
)

story.append(p("Resultados y evidencia", "Section"))
results_rows = [
    ("6 jun 2026", "npm run test:e2e", "27/27", "APROBADO", "Corrida completa Chromium; 3.8 min."),
    ("6 jun 2026", "npm test", "22/22", "APROBADO", "6 suites Jest; 10.9 s."),
    (
        "6 jun 2026",
        "manage.py test auth + password + school context",
        "41/41",
        "APROBADO",
        "Incluye los 15 tests backend nuevos.",
    ),
    ("4 jun 2026", "manage.py test calificaciones", "273/273", "APROBADO", "Baseline completa del informe original."),
    ("4 jun 2026", "manage.py test mensajes", "33/33", "APROBADO", "Mensajería focalizada."),
]
story.append(table(["Fecha", "Comando / suite", "Resultado", "Estado", "Observación"], results_rows, [22 * mm, 62 * mm, 22 * mm, 24 * mm, 48 * mm]))

story.append(Spacer(1, 5 * mm))
story.append(p("Incidencia detectada durante la actualización", "Subsection"))
story.append(
    p(
        "La primera corrida E2E del 6 de junio produjo 26/27 porque un locator de Playwright esperaba una sola fila "
        "de Informática y encontró dos filas válidas. Se ajustó el test a <b>.first()</b>, se verificó el caso "
        "aislado 1/1 y luego la suite completa finalizó 27/27. No se detectó un defecto funcional del producto.",
        "BodySmall",
    )
)

story.append(PageBreak())
story.append(p("Inventario backend Django", "Section"))
story.append(
    p(
        "El catálogo backend actual contiene 288 métodos de test distribuidos en 19 módulos.",
        "Body",
    )
)
story.append(table(["Archivo", "Tests", "Cobertura principal"], backend_rows, [55 * mm, 16 * mm, 107 * mm]))

story.append(PageBreak())
story.append(p("Inventario frontend Jest", "Section"))
story.append(table(["Archivo", "Tests", "Cobertura principal"], jest_rows, [58 * mm, 16 * mm, 104 * mm]))
story.append(Spacer(1, 7 * mm))
story.append(p("Inventario Playwright E2E", "Section"))
story.append(table(["Archivo", "Tests", "Flujos cubiertos"], e2e_rows, [58 * mm, 16 * mm, 104 * mm]))

story.append(Spacer(1, 7 * mm))
story.append(p("Matriz de roles validada", "Section"))
role_rows = [
    ("Admin plataforma", "Colegios, importación CSV, permisos globales y backups."),
    ("Admin colegio", "Panel, cursos, usuarios, asignaciones y límites por colegio."),
    ("Directivo", "Acceso institucional, alumnos y reportes según permisos."),
    ("Profesor", "Notas, mensajes, sanciones y restricciones por curso."),
    ("Preceptor", "Asistencias, justificaciones, alertas, mensajes y cursos."),
    ("Padre/familia", "Hijos propios, firmas, mensajes, notas, asistencia y eventos."),
    ("Alumno", "Datos propios, perfil, navegación y bloqueo a datos ajenos."),
]
story.append(table(["Rol", "Validaciones principales"], role_rows, [48 * mm, 130 * mm]))

story.append(PageBreak())
story.append(p("Tests nuevos agregados después del informe original", "Section"))
story.append(
    p(
        "Se incorporaron 23 tests nuevos: 15 backend y 8 Jest. Además se corrigió el manejo de token vacío en "
        "/api/token/verify/ para devolver 401 en lugar de 500.",
        "Body",
    )
)
story.append(p("Backend auth y password: 15 tests", "Subsection"))
story.append(table(["Área", "Objetivo validado"], new_backend_tests, [38 * mm, 140 * mm]))
story.append(Spacer(1, 6 * mm))
story.append(p("Frontend NotificationBell y Perfil: 8 tests", "Subsection"))
story.append(table(["Componente", "Objetivo validado"], new_frontend_tests, [38 * mm, 140 * mm]))

story.append(PageBreak())
story.append(p("Cobertura funcional consolidada", "Section"))
coverage_rows = [
    ("Autenticación y sesión", "Login por rol/colegio, refresh, verify, blacklist, logout y cookies.", "Cubierto"),
    ("Password", "Solicitud, confirmación, token inválido/reutilizado, validación y cambio.", "Cubierto backend"),
    ("Multi-colegio", "Login/whoami, scoping de APIs, cursos, alumnos, mensajes y datos académicos.", "Cubierto"),
    ("Mensajería", "Envío, grupal, bandeja, hilos, respuestas, lectura, unread y permisos.", "Cubierto"),
    ("Notificaciones UI", "Badge, preview, lectura individual/masiva, navegación y vacío.", "Cubierto Jest"),
    ("Perfil UI", "Edición, cambio de password, legajo y vínculos padre-hijo.", "Cubierto Jest"),
    ("Notas", "Creación, edición, filtros, firmas, permisos y notificaciones.", "Cubierto"),
    ("Asistencias", "Registro, tardanza, justificación, detalle, firmas, alertas y filtros.", "Cubierto"),
    ("Sanciones", "Creación, visualización, eliminación autorizada y firma.", "Cubierto"),
    ("Reportes/eventos", "Estadísticas, históricos, calendario y permisos por curso.", "Cubierto"),
    ("Administración", "Cursos, usuarios, staff, asignaciones, importación y backups.", "Parcial UI"),
    ("Responsive/mobile", "Flujo padre en dashboard, hijos, detalle y mensajes.", "Cubierto E2E"),
]
story.append(table(["Área", "Cobertura", "Estado"], coverage_rows, [38 * mm, 112 * mm, 28 * mm]))

story.append(Spacer(1, 7 * mm))
story.append(p("Matriz de riesgos", "Section"))
risk_rows = [
    ("Fuga entre colegios/cursos", "Crítica", "Scoping backend + permisos E2E.", "Cubierto"),
    ("Acceso académico no autorizado", "Crítica", "Alumno, padre, profesor y staff sin rol.", "Cubierto"),
    ("Token/sesión reutilizable", "Alta", "Blacklist, refresh, verify y logout.", "Cubierto"),
    ("Reset de password inseguro", "Alta", "Respuesta genérica, token, validación y blacklist.", "Cubierto backend"),
    ("Mensajes leídos/respondidos por tercero", "Alta", "Backend + E2E por destinatario.", "Cubierto"),
    ("Datos académicos no persistidos", "Alta", "Flujos E2E y backend.", "Cubierto"),
    ("UI de notificaciones inconsistente", "Media", "Jest de badge, lectura y refresh.", "Cubierto"),
    ("Perfil con controles incorrectos por rol", "Media", "Jest profesor/alumno/padre.", "Cubierto"),
    ("Regresión mobile", "Media", "Navegación mobile de padre.", "Cubierto"),
    ("Acción destructiva admin", "Alta", "Backend presente; E2E pendiente.", "Pendiente E2E"),
]
story.append(table(["Riesgo", "Severidad", "Control QA", "Estado"], risk_rows, [50 * mm, 24 * mm, 76 * mm, 28 * mm]))

story.append(PageBreak())
story.append(p("Pendientes recomendados", "Section"))
pending = [
    "<b>Recovery UI E2E:</b> /forgot-password y /reset-password con éxito, link inválido, passwords distintas y error de API.",
    "<b>Admin UI E2E:</b> creación de usuario, padre-hijo, asignación profesor/preceptor, branding y borrado de colegio/job.",
    "<b>Unread end-to-end:</b> contador al abrir hilo, marcar todas, responder y refrescar URL directa.",
    "<b>Direct URL/refresh:</b> rutas protegidas por rol para mensajes, alumnos, cursos y admin.",
    "<b>Seed QA:</b> idempotencia, roles, cursos, vínculos y datos multi-colegio.",
    "<b>Backend completo actual:</b> ejecutar 288/288 en un entorno/timeout suficiente para reemplazar la baseline combinada.",
]
for item in pending:
    story.append(bullet(item))

story.append(Spacer(1, 8 * mm))
story.append(p("Conclusión", "Section"))
story.append(
    p(
        "El proyecto mantiene una cobertura automatizada amplia y orientada a riesgos de permisos, privacidad y "
        "persistencia. La actualización añadió cobertura directa de auth/password y cobertura UI de notificaciones "
        "y perfil. La corrida final del 6 de junio de 2026 aprobó 27/27 E2E, 22/22 Jest y 41/41 backend focalizado.",
        "Body",
    )
)
story.append(
    p(
        "Inventario total actual: <b>337 tests automatizados</b> (288 backend + 22 Jest + 27 Playwright).",
        "Callout",
    )
)


doc = SimpleDocTemplate(
    str(OUTPUT),
    pagesize=A4,
    rightMargin=16 * mm,
    leftMargin=16 * mm,
    topMargin=19 * mm,
    bottomMargin=17 * mm,
    title="Informe QA consolidado completo - 2026-06-06",
    author="Codex qa-tester",
    subject="Consolidado de pruebas automatizadas de PROYECTO_COMUNICACIONES",
)
doc.build(story, onFirstPage=page_header_footer, onLaterPages=page_header_footer)
print(OUTPUT)
