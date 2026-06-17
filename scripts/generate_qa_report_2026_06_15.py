from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "qa-reporte-consolidado-2026-06-15.pdf"

NAVY = colors.HexColor("#0B1B3F")
BLUE = colors.HexColor("#1D4ED8")
GREEN = colors.HexColor("#15803D")
LIGHT_GREEN = colors.HexColor("#DCFCE7")
LIGHT_GRAY = colors.HexColor("#F3F4F6")
MID_GRAY = colors.HexColor("#D1D5DB")
AMBER = colors.HexColor("#B45309")
LIGHT_AMBER = colors.HexColor("#FEF3C7")
RED = colors.HexColor("#B91C1C")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], fontSize=21, leading=25, textColor=NAVY))
styles.add(ParagraphStyle(name="Subtitle", parent=styles["Normal"], fontSize=10, leading=14, textColor=colors.HexColor("#374151")))
styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], fontSize=14, leading=18, textColor=NAVY, spaceBefore=8, spaceAfter=7))
styles.add(ParagraphStyle(name="Subsection", parent=styles["Heading3"], fontSize=11, leading=14, textColor=BLUE, spaceBefore=6, spaceAfter=4))
styles.add(ParagraphStyle(name="BodyReport", parent=styles["BodyText"], fontSize=9, leading=13, textColor=colors.HexColor("#1F2937"), spaceAfter=5))
styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=7.7, leading=10.5, textColor=colors.HexColor("#1F2937")))
styles.add(ParagraphStyle(name="Cell", parent=styles["BodyText"], fontSize=7.2, leading=9.5, textColor=colors.HexColor("#111827")))
styles.add(ParagraphStyle(name="HeaderCell", parent=styles["Cell"], fontName="Helvetica-Bold", textColor=colors.white, alignment=TA_CENTER))
styles.add(ParagraphStyle(name="Metric", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=17, leading=19, alignment=TA_CENTER, textColor=GREEN))
styles.add(ParagraphStyle(name="MetricLabel", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=9, leading=11, alignment=TA_CENTER, textColor=NAVY))


def p(text, style="BodyReport"):
    return Paragraph(text, styles[style])


def bullet(text):
    return Paragraph(f"• {text}", styles["BodyReport"])


def make_table(headers, rows, widths):
    data = [[Paragraph(str(value), styles["HeaderCell"]) for value in headers]]
    for row in rows:
        data.append([value if isinstance(value, Paragraph) else Paragraph(str(value), styles["Cell"]) for value in row])
    result = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("GRID", (0, 0), (-1, -1), 0.35, MID_GRAY),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return result


def metric_box(label, value, note):
    table = Table(
        [[p(label, "MetricLabel")], [p(value, "Metric")], [p(note, "Small")]],
        colWidths=[56 * mm],
        rowHeights=[9 * mm, 12 * mm, 13 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GREEN),
                ("BOX", (0, 0), (-1, -1), 0.8, GREEN),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def header_footer(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(MID_GRAY)
    canvas.line(16 * mm, height - 14 * mm, width - 16 * mm, height - 14 * mm)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(NAVY)
    canvas.drawString(16 * mm, height - 10.5 * mm, "PROYECTO_COMUNICACIONES - Informe QA consolidado")
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#4B5563"))
    canvas.drawRightString(width - 16 * mm, height - 10.5 * mm, "15 de junio de 2026")
    canvas.line(16 * mm, 13 * mm, width - 16 * mm, 13 * mm)
    canvas.drawString(16 * mm, 8.5 * mm, "Skill qa-tester | Ambiente local QA")
    canvas.drawRightString(width - 16 * mm, 8.5 * mm, f"Página {doc.page}")
    canvas.restoreState()


recorded_runs = [
    ("Backend base completa", "273/273", "Aprobado", "Baseline registrada el 4 de junio."),
    ("Backend mensajería focalizada", "33/33", "Aprobado", "Baseline inicial de mensajería."),
    ("Backend focalizado", "44/44", "Aprobado", "Bloque funcional registrado."),
    ("Backend alumnos, contexto y auth", "70/70", "Aprobado", "Permisos y aislamiento escolar."),
    ("Backend auth/password/contexto/backups", "57/57", "Aprobado", "Seguridad y restaurabilidad."),
    ("Backend mensajes/notificaciones", "37/37", "Aprobado", "Luego mensajes quedó en 38/38."),
    ("Backend alumnos", "36/36", "Aprobado", "Importación, scoping y límites."),
    ("Backend notas/asistencias/sanciones", "65/65", "Aprobado", "Regresión de firmas atómicas."),
    ("Backend Directivo multi-colegio", "112/112", "Aprobado", "Auth, contexto, alumnos, reportes, admin y seed."),
    ("Backend administración actual", "21/21", "Aprobado", "Incluye edición segura de usuarios."),
    ("Backend notas actual", "21/21", "Aprobado", "Incluye conflicto 409 por edición obsoleta."),
    ("Backend firmas", "10/10", "Aprobado", "Reclamo atómico de firma."),
    ("Backend rendimiento masivo", "2/2", "Aprobado", "100 altas y actualizaciones, máximo 8 consultas."),
    ("Backend seed QA", "3/3", "Aprobado", "Idempotencia y aislamiento."),
    ("Backend password", "12/12", "Aprobado", "Reset y cambio de contraseña."),
    ("Jest actual", "35/35", "Aprobado", "12 suites frontend."),
    ("Jest registrado previo", "33/33", "Aprobado", "Regresiones previas de frontend."),
    ("Playwright base", "27/27", "Aprobado", "Baseline funcional inicial."),
    ("Playwright regresión general", "49/49", "Aprobado", "Flujos principales."),
    ("Playwright alumnos y mensajes", "20/20", "Aprobado", "Flujos focalizados."),
    ("Playwright familia/cursos/rutas", "15/15", "Aprobado", "Refresh y acceso directo."),
    ("Playwright resiliencia admin", "10/10 por navegador", "Aprobado", "Chromium y Firefox."),
    ("Playwright plataforma resiliente", "10/10 por navegador", "Aprobado", "Chromium y Firefox."),
    ("Playwright onboarding plataforma", "12/12 por navegador", "Aprobado", "Colegios y administradores."),
    ("Playwright accesibilidad admin", "8/8 por navegador", "Aprobado", "Teclado, anuncios y diálogos."),
    ("Playwright recuperación password", "9/9 ejecutados", "Aprobado", "Una integración real omitida en Firefox."),
    ("Playwright unread/rutas directas", "22/22", "Aprobado", "Chromium y Firefox."),
    ("Playwright administración escolar", "14/14", "Aprobado", "Chromium y Firefox."),
    ("Playwright semántica protegida", "10/10 por navegador", "Aprobado", "35 rutas o recorridos."),
    ("Playwright teclado/lector", "9/9 por navegador", "Aprobado", "Semántica asistida, no lector real."),
    ("Playwright WCAG/zoom", "7/7 por navegador", "Aprobado", "Sin violaciones serias/críticas."),
    ("Playwright Firefox crítico", "17/17", "Aprobado", "Regresión de seguridad y administración."),
    ("Playwright edición concurrente", "1/1 Chromium", "Aprobado", "Primera edición 200, obsoleta 409."),
    ("Playwright Directivo", "1/1 Chromium", "Aprobado", "Login sin privilegios administrativos."),
    ("Playwright edición admin", "1/1 Chromium", "Aprobado", "Nombre, apellido y email persistidos."),
    ("Build Next.js", "40 páginas", "Aprobado", "Compilación y validación de tipos."),
]

functional_coverage = [
    ("Autenticación", "Login por rol/colegio, logout, refresh, verify, blacklist, cookies y throttling.", "Cubierto"),
    ("Multi-colegio", "Aislamiento, branding, Directivos con membresía y selector de colegio.", "Cubierto"),
    ("Alumnos", "Alta, importación, detalle, legajos, transferencia e historial.", "Cubierto"),
    ("Notas", "Creación, edición, filtros, firmas, permisos y versionado optimista.", "Cubierto"),
    ("Asistencia", "Registro, tardanza, ausencia, justificación, alertas y firmas.", "Cubierto"),
    ("Sanciones", "Alta, lectura, permisos, borrado autorizado y firmas.", "Cubierto"),
    ("Mensajería", "Inbox, hilos, privacidad, grupales, lectura, respuestas e idempotencia.", "Cubierto"),
    ("Notificaciones", "Preview, badges, lectura individual/masiva y sincronización entre pestañas.", "Cubierto"),
    ("Administración escolar", "Usuarios, edición de datos, cursos, asignaciones y vínculos familiares.", "Cubierto"),
    ("Administración plataforma", "Colegios, admins, importación, branding, backups y borrado async.", "Cubierto"),
    ("Reportes y eventos", "Permisos por rol/curso, históricos, filtros y calendario.", "Cubierto"),
    ("Accesibilidad", "WCAG automatizada, teclado, foco, headings, landmarks, zoom y reflow.", "Cubierto automatizado"),
    ("Responsive", "Desktop, tablet, mobile, landscape, descargas y controles táctiles.", "Cubierto"),
    ("Resiliencia", "Carga, vacío, errores HTTP, detalle del backend y reintentos.", "Cubierto"),
    ("Datos QA", "Seed idempotente, limpieza automática y aislamiento de otro tenant.", "Cubierto"),
]

findings_fixed = [
    ("Alta", "Vinculación de legajo sin colegio activo podía intentar cruzar tenants.", "Corregido y probado."),
    ("Alta", "Asignaciones filtradas podían eliminar profesores no visibles en la búsqueda.", "Corregido y probado."),
    ("Alta", "Backup SQLite podía omitir transacciones confirmadas en WAL.", "Backup nativo y restauración comprobada."),
    ("Alta", "Login no tenía throttle efectivo.", "Throttle por IP y usuario."),
    ("Alta", "Firmas concurrentes podían responder éxito dos veces.", "Actualización condicional atómica."),
    ("Alta", "Respuestas de mensajes podían duplicarse por retry/fallback.", "Client request ID e idempotencia."),
    ("Alta", "Ediciones concurrentes de notas se sobrescribían.", "Versionado optimista y HTTP 409."),
    ("Alta", "Directivo no tenía pertenencia institucional multi-colegio.", "Membresía institucional independiente."),
    ("Media", "Rutas administrativas sin permiso quedaban cargando indefinidamente.", "Estado Acceso restringido."),
    ("Media", "Errores/éxitos administrativos no se anunciaban.", "Roles alert/status y aria-live."),
    ("Media", "Diálogos no restauraban foco consistentemente.", "Restauración explícita y Escape."),
    ("Media", "Mobile Mensajes desbordaba horizontalmente.", "Grid corregido con min-width: 0."),
    ("Media", "Encabezados y landmarks inconsistentes en rutas protegidas.", "Matriz semántica de 35 recorridos."),
    ("Media", "Directorio no permitía editar datos personales.", "PATCH seguro y diálogo de edición."),
]

performance_rows = [
    ("Lectura concurrente inicial", "500", "25", "0", "145,76 req/s", "274,06 ms", "677,77 ms"),
    ("Lectura concurrente ampliada", "2.000", "40", "0", "155,85 req/s", "723,77 ms", "1.205,64 ms"),
    ("Soak local", "10.000", "40", "0", "158,29 req/s", "716,26 ms", "1.214,42 ms"),
]

pending_rows = [
    ("Correo real", "Resend sin credenciales operativas ni dominio/remitente verificado.", "Entrega, rebotes, spam y reintentos."),
    ("PostgreSQL", "Servicio 18 activo, pero SCRAM requiere credenciales no disponibles.", "Carga de horas y escrituras concurrentes."),
    ("WebKit/Safari", "Ejecutable no instalado; descarga bloqueada previamente por TLS/CA.", "Regresión integral Safari/WebKit."),
    ("Lector de pantalla", "NVDA no está instalado.", "Sesión manual con NVDA, JAWS o VoiceOver."),
]

story = [
    Spacer(1, 7 * mm),
    p("Informe QA consolidado", "ReportTitle"),
    p(
        "Resultados registrados desde el 3 hasta el 15 de junio de 2026 para "
        "PROYECTO_COMUNICACIONES. El informe consolida pruebas backend, Jest, "
        "Playwright, accesibilidad, seguridad, rendimiento y validaciones manuales.",
        "Subtitle",
    ),
    Spacer(1, 5 * mm),
]

metrics = Table(
    [[
        metric_box("Backend definido", "328", "Métodos de test actuales"),
        metric_box("Jest definido", "35", "Tests frontend actuales"),
        metric_box("E2E declarado", "106", "Casos base; algunos parametrizados"),
    ]],
    colWidths=[59 * mm, 59 * mm, 59 * mm],
)
metrics.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 1), ("RIGHTPADDING", (0, 0), (-1, -1), 1)]))
story.extend([metrics, Spacer(1, 6 * mm)])

story.extend([
    p("Resumen ejecutivo", "Section"),
    p(
        "<b>Estado general: aprobado con dependencias externas pendientes.</b> "
        "La cobertura funcional y técnica estimada se mantiene entre 93 % y 95 %. "
        "Chromium y Firefox cuentan con regresiones extensas aprobadas. Las cifras de "
        "corridas listadas a continuación se superponen por módulos, navegadores y fechas; "
        "no deben sumarse como si fueran una única ejecución.",
    ),
    p(
        "El inventario actual contiene 328 tests backend, 35 Jest y 106 declaraciones "
        "Playwright. Los casos E2E parametrizados generan más ejecuciones reales al correr "
        "varios navegadores, roles y viewports.",
        "Small",
    ),
    p("Resultados de todas las corridas registradas", "Section"),
    make_table(["Suite o bloque", "Resultado", "Estado", "Alcance"], recorded_runs, [54 * mm, 28 * mm, 25 * mm, 71 * mm]),
    PageBreak(),
    p("Cobertura funcional", "Section"),
    make_table(["Área", "Validaciones principales", "Estado"], functional_coverage, [38 * mm, 112 * mm, 28 * mm]),
    Spacer(1, 7 * mm),
    p("Hallazgos corregidos", "Section"),
    make_table(["Severidad", "Hallazgo", "Resolución"], findings_fixed, [23 * mm, 91 * mm, 64 * mm]),
    PageBreak(),
    p("Rendimiento y estabilidad", "Section"),
    make_table(
        ["Corrida", "Requests", "Conc.", "Errores", "Rendimiento", "p95", "p99"],
        performance_rows,
        [42 * mm, 20 * mm, 17 * mm, 18 * mm, 31 * mm, 25 * mm, 25 * mm],
    ),
    Spacer(1, 5 * mm),
    bullet("La corrida sostenida duró 63,18 segundos y completó 10.000 respuestas HTTP 200."),
    bullet("Memoria residente: +1,68 MB; memoria privada: +0,94 MB durante la ventana medida."),
    bullet("Las operaciones masivas de 100 asistencias se mantuvieron en un máximo de 8 consultas SQL."),
    bullet("Estas mediciones corresponden al servidor de desarrollo local con SQLite y lecturas."),
    p("Accesibilidad y compatibilidad", "Section"),
    bullet("Chromium y Firefox: matrices de desktop, tablet, mobile y landscape aprobadas."),
    bullet("WCAG 2 A/AA automatizada: 7/7 por navegador, sin violaciones serias o críticas en las rutas auditadas."),
    bullet("Teclado, foco, skip link, diálogos, anuncios y encabezados: 9/9 por navegador."),
    bullet("Semántica de rutas protegidas: 10/10 por navegador, 35 rutas o recorridos."),
    bullet("PDF de notas, sanciones e inasistencias validado por nombre, tamaño y firma binaria."),
    p("Bloqueos pendientes", "Section"),
    make_table(["Pendiente", "Bloqueo verificado", "Validación faltante"], pending_rows, [36 * mm, 78 * mm, 64 * mm]),
    Spacer(1, 6 * mm),
    p("Conclusión", "Section"),
    p(
        "No hay una regresión funcional crítica abierta confirmada en los bloques ejecutables. "
        "Los pendientes restantes dependen de credenciales, proveedores o software externo. "
        "El correo real continúa registrado como falla operativa esperada hasta conectar un "
        "proveedor. PostgreSQL, WebKit/Safari y una sesión manual con lector de pantalla deben "
        "completarse cuando la infraestructura correspondiente esté disponible.",
    ),
    p(
        "Fuentes: docs/QA_ESTADO_ACTUAL.md, reportes QA previos, resultados JSON de benchmark "
        "y salidas de regresiones ejecutadas durante las sesiones de qa-tester.",
        "Small",
    ),
])

doc = SimpleDocTemplate(
    str(OUTPUT),
    pagesize=A4,
    leftMargin=16 * mm,
    rightMargin=16 * mm,
    topMargin=19 * mm,
    bottomMargin=17 * mm,
    title="Informe QA consolidado - 2026-06-15",
    author="Codex qa-tester",
    subject="Resultados consolidados de QA de PROYECTO_COMUNICACIONES",
)
doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
print(OUTPUT)
