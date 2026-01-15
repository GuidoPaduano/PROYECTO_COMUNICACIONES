from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


# ============================================================
# ✅ FIX: Validator requerido por migraciones viejas (0014/0015)
# ============================================================
def validate_calificacion_ext(value):
    """
    Este validador existe porque migraciones anteriores (0014/0015)
    lo referencian como calificaciones.models.validate_calificacion_ext.

    Acepta:
      - 1 a 10 (enteros o decimales con hasta 2 decimales)
      - TEA / TEP / TED
      - NO ENTREGADO
    """
    if value is None:
        raise ValidationError("La calificación no puede estar vacía.")

    s = str(value).strip()
    if not s:
        raise ValidationError("La calificación no puede estar vacía.")

    up = s.upper()

    allowed_text = {"TEA", "TEP", "TED", "NO ENTREGADO"}
    if up in allowed_text:
        return

    # soportar coma decimal
    num_str = s.replace(",", ".")
    try:
        num = float(num_str)
    except Exception:
        raise ValidationError("Calificación inválida. Usá 1-10 o TEA/TEP/TED/NO ENTREGADO.")

    if not (1 <= num <= 10):
        raise ValidationError("La calificación numérica debe estar entre 1 y 10.")

    # hasta 2 decimales
    if "." in num_str:
        dec = num_str.split(".", 1)[1]
        if len(dec) > 2:
            raise ValidationError("La calificación puede tener como máximo 2 decimales.")


class Alumno(models.Model):
    # ✅ No achicamos curso a 2 porque tu DB ya tiene valores tipo 5NAT/4ECO, etc.
    CURSOS = [
        # Formato corto
        ('1A', '1A'), ('1B', '1B'),
        ('2A', '2A'), ('2B', '2B'),
        ('3A', '3A'), ('3B', '3B'),
        ('4A', '4A'), ('4B', '4B'),
        ('5A', '5A'), ('5B', '5B'),
        ('6A', '6A'), ('6B', '6B'),

        # Formato largo (legacy)
        ('4ECO', '4ECO'), ('4NAT', '4NAT'),
        ('5ECO', '5ECO'), ('5NAT', '5NAT'),
        ('6ECO', '6ECO'), ('6NAT', '6NAT'),
    ]

    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100, default="", blank=True)
    id_alumno = models.CharField(max_length=20, unique=True)  # ID/Legajo único

    # ✅ clave: max_length grande para NO romper al migrar
    curso = models.CharField(max_length=20, choices=CURSOS, db_index=True)

    padre = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="alumnos_como_padre")

    usuario = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="perfil_alumno")

    def __str__(self):
        if self.apellido:
            return f"{self.apellido}, {self.nombre} ({self.curso})"
        return f"{self.nombre} ({self.curso})"


class Nota(models.Model):
    MATERIAS = [
        ('Lengua', 'Lengua'),
        ('Matemática', 'Matemática'),
        ('Ciencias', 'Ciencias'),
        ('Historia', 'Historia'),
        ('Geografía', 'Geografía'),
        ('Inglés', 'Inglés'),
        ('Educación Física', 'Educación Física'),
        ('Música', 'Música'),
        ('Plástica', 'Plástica'),
        ('Catequesis', 'Catequesis'),
        ('Informática', 'Informática'),
    ]

    TIPOS = [
        ('Examen', 'Examen'),
        ('Trabajo Práctico', 'Trabajo Práctico'),
        ('Participación', 'Participación'),
        ('Tarea', 'Tarea'),
    ]

    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name="notas")
    materia = models.CharField(max_length=50, choices=MATERIAS)
    tipo = models.CharField(max_length=50, choices=TIPOS)

    # ✅ CLAVE: CharField para permitir "TEA/TEP/TED/NO ENTREGADO" y también "7" / "8.50"
    calificacion = models.CharField(
        max_length=15,
        validators=[validate_calificacion_ext],
    )

    cuatrimestre = models.IntegerField(choices=[(1, "1"), (2, "2")])
    fecha = models.DateField(default=timezone.now)
    observaciones = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"{self.alumno} - {self.materia}: {self.calificacion}"


class Mensaje(models.Model):
    REMITENTE_TIPOS = [
        ('Profesor', 'Profesor'),
        ('Preceptor', 'Preceptor'),
        ('Directivo', 'Directivo'),
    ]

    remitente = models.ForeignKey(User, on_delete=models.CASCADE, related_name="mensajes_enviados")
    destinatario = models.ForeignKey(User, on_delete=models.CASCADE, related_name="mensajes_recibidos")

    # ✅ max_length grande para legacy
    curso = models.CharField(max_length=20, blank=True, null=True, db_index=True)

    # ✅ default para evitar prompts si hay filas viejas
    tipo_remitente = models.CharField(max_length=20, choices=REMITENTE_TIPOS, default="Profesor")

    asunto = models.CharField(max_length=255)
    contenido = models.TextField()
    fecha_envio = models.DateTimeField(auto_now_add=True)
    leido = models.BooleanField(default=False)

    class Meta:
        ordering = ["-fecha_envio", "-id"]

    def __str__(self):
        return f"{self.asunto} ({self.remitente} -> {self.destinatario})"


class Comunicado(models.Model):
    remitente = models.ForeignKey(User, on_delete=models.CASCADE)

    # ✅ max_length grande
    curso = models.CharField(max_length=20, blank=True, null=True, db_index=True)

    titulo = models.CharField(max_length=255)
    contenido = models.TextField()
    fecha_envio = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha_envio", "-id"]

    def __str__(self):
        return f"{self.titulo} ({self.curso})"


class Sancion(models.Model):
    TIPOS = [
        ('Amonestación', 'Amonestación'),
        ('Llamado de atención', 'Llamado de atención'),
        ('Suspensión', 'Suspensión'),
    ]

    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name="sanciones")

    # ✅ default para evitar prompts
    tipo = models.CharField(max_length=50, choices=TIPOS, default="Amonestación")

    motivo = models.TextField()
    detalle = models.TextField(blank=True, null=True)
    fecha = models.DateField(default=timezone.now)
    docente = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"{self.alumno} - {self.tipo} ({self.fecha})"


TIPOS_EVENTO = [
    ('Evaluación', 'Evaluación'),
    ('Entrega', 'Entrega'),
    ('Acto', 'Acto'),
    ('Reunión', 'Reunión'),
    ('Otro', 'Otro'),
]


class Evento(models.Model):
    titulo = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)

    # ✅ max_length grande (no varchar(2))
    curso = models.CharField(max_length=20, choices=Alumno.CURSOS, db_index=True)

    fecha = models.DateField()
    tipo_evento = models.CharField(max_length=50, choices=TIPOS_EVENTO, default='Otro')

    class Meta:
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"{self.titulo} ({self.fecha})"


# =========================
# Asistencias
# =========================
TIPOS_ASISTENCIA = (
    ("clases", "Clases"),
    ("informatica", "Informática"),
    ("catequesis", "Catequesis"),
)


class Asistencia(models.Model):
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name="asistencias")
    fecha = models.DateField(default=timezone.localdate, db_index=True)
    tipo_asistencia = models.CharField(
        max_length=20,
        choices=TIPOS_ASISTENCIA,
        default="clases",
        db_index=True,
    )
    presente = models.BooleanField(default=True)
    tarde = models.BooleanField(default=False, db_index=True)
    justificada = models.BooleanField(default=False, db_index=True)
    observacion = models.CharField(max_length=255, blank=True, null=True)
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    # ✅ default=timezone.now evita prompts de auto_now_add en tablas con filas existentes
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-fecha", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["alumno", "fecha", "tipo_asistencia"],
                name="unique_asistencia_alumno_fecha_tipo",
            ),
            models.CheckConstraint(
                check=(models.Q(tarde=False) | models.Q(presente=True)),
                name="asistencia_tarde_requiere_presente",
            ),
            models.CheckConstraint(
                check=(models.Q(justificada=False) | models.Q(presente=False) | models.Q(tarde=True)),
                name="asistencia_justificada_requiere_ausente_o_tarde",
            ),
        ]
        indexes = [
            models.Index(fields=["alumno", "fecha", "tipo_asistencia"]),
        ]

    def __str__(self):
        estado = "Ausente" if (not self.presente) else ("Tarde" if getattr(self, "tarde", False) else "Presente")
        return f"{self.alumno} - {self.fecha} - {self.tipo_asistencia} - {estado}"

# ------------------------------------------------------------
# Notificaciones (campana / inbox UI)
# ------------------------------------------------------------

class Notificacion(models.Model):
    TIPO_CHOICES = [
        ("nota", "Nota"),
        ("sancion", "Sanción"),
        ("inasistencia", "Inasistencia"),
        ("mensaje", "Mensaje"),
        ("evento", "Evento"),
        ("otro", "Otro"),
    ]

    destinatario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notificaciones",
        db_index=True,
    )
    tipo = models.CharField(max_length=30, choices=TIPO_CHOICES, db_index=True)
    titulo = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    url = models.CharField(max_length=500, blank=True, null=True)
    creada_en = models.DateTimeField(auto_now_add=True, db_index=True)
    leida = models.BooleanField(default=False, db_index=True)
    meta = models.JSONField(blank=True, null=True)

    class Meta:
        ordering = ["-creada_en"]

    def __str__(self):
        return f"{self.tipo}: {self.titulo}"
