from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator


# ============================================================
# âœ… FIX: Validator requerido por migraciones viejas (0014/0015)
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
        raise ValidationError("La calificaciÃ³n no puede estar vacÃ­a.")

    s = str(value).strip()
    if not s:
        raise ValidationError("La calificaciÃ³n no puede estar vacÃ­a.")

    up = s.upper()

    allowed_text = {"TEA", "TEP", "TED", "NO ENTREGADO"}
    if up in allowed_text:
        return

    # soportar coma decimal
    num_str = s.replace(",", ".")
    try:
        num = float(num_str)
    except Exception:
        raise ValidationError("CalificaciÃ³n invÃ¡lida. UsÃ¡ 1-10 o TEA/TEP/TED/NO ENTREGADO.")

    if not (1 <= num <= 10):
        raise ValidationError("La calificaciÃ³n numÃ©rica debe estar entre 1 y 10.")

    # hasta 2 decimales
    if "." in num_str:
        dec = num_str.split(".", 1)[1]
        if len(dec) > 2:
            raise ValidationError("La calificaciÃ³n puede tener como mÃ¡ximo 2 decimales.")


class Alumno(models.Model):
    # âœ… No achicamos curso a 2 porque tu DB ya tiene valores tipo 5NAT/4ECO, etc.
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
    id_alumno = models.CharField(max_length=20, unique=True)  # ID/Legajo Ãºnico

    # âœ… clave: max_length grande para NO romper al migrar
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
        ('MatemÃ¡tica', 'MatemÃ¡tica'),
        ('Ciencias', 'Ciencias'),
        ('Historia', 'Historia'),
        ('GeografÃ­a', 'GeografÃ­a'),
        ('InglÃ©s', 'InglÃ©s'),
        ('EducaciÃ³n FÃ­sica', 'EducaciÃ³n FÃ­sica'),
        ('MÃºsica', 'MÃºsica'),
        ('PlÃ¡stica', 'PlÃ¡stica'),
        ('Catequesis', 'Catequesis'),
        ('InformÃ¡tica', 'InformÃ¡tica'),
    ]

    TIPOS = [
        ('Examen', 'Examen'),
        ('Trabajo PrÃ¡ctico', 'Trabajo PrÃ¡ctico'),
        ('ParticipaciÃ³n', 'ParticipaciÃ³n'),
        ('Tarea', 'Tarea'),
    ]
    RESULTADO_CHOICES = [
        ("TEA", "Aprobado"),
        ("TEP", "Desaprobado"),
        ("TED", "Aplazado"),
    ]

    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name="notas")
    materia = models.CharField(max_length=50, choices=MATERIAS)
    tipo = models.CharField(max_length=50, choices=TIPOS)

    # âœ… CLAVE: CharField para permitir "TEA/TEP/TED/NO ENTREGADO" y tambiÃ©n "7" / "8.50"
    calificacion = models.CharField(
        max_length=15,
        validators=[validate_calificacion_ext],
    )
    resultado = models.CharField(
        max_length=3,
        choices=RESULTADO_CHOICES,
        null=True,
        blank=True,
        db_index=True,
    )
    nota_numerica = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
    )

    cuatrimestre = models.IntegerField(choices=[(1, "1"), (2, "2")])
    fecha = models.DateField(default=timezone.now)
    observaciones = models.TextField(blank=True, null=True)
    firmada = models.BooleanField(default=False, db_index=True)
    firmada_en = models.DateTimeField(null=True, blank=True)
    firmada_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notas_firmadas",
    )

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

    # âœ… max_length grande para legacy
    curso = models.CharField(max_length=20, blank=True, null=True, db_index=True)

    # âœ… default para evitar prompts si hay filas viejas
    tipo_remitente = models.CharField(max_length=20, choices=REMITENTE_TIPOS, default="Profesor")

    asunto = models.CharField(max_length=255)
    contenido = models.TextField()
    fecha_envio = models.DateTimeField(auto_now_add=True)
    leido = models.BooleanField(default=False)

    class Meta:
        ordering = ["-fecha_envio", "-id"]
        indexes = [
            models.Index(fields=["destinatario", "leido", "fecha_envio"]),
            models.Index(fields=["destinatario", "fecha_envio"]),
            models.Index(fields=["remitente", "fecha_envio"]),
        ]

    def __str__(self):
        return f"{self.asunto} ({self.remitente} -> {self.destinatario})"


class Comunicado(models.Model):
    remitente = models.ForeignKey(User, on_delete=models.CASCADE)

    # âœ… max_length grande
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
        ('AmonestaciÃ³n', 'AmonestaciÃ³n'),
        ('Llamado de atenciÃ³n', 'Llamado de atenciÃ³n'),
        ('SuspensiÃ³n', 'SuspensiÃ³n'),
    ]

    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name="sanciones")

    # âœ… default para evitar prompts
    tipo = models.CharField(max_length=50, choices=TIPOS, default="AmonestaciÃ³n")

    motivo = models.TextField()
    detalle = models.TextField(blank=True, null=True)
    fecha = models.DateField(default=timezone.now)
    docente = models.CharField(max_length=100, blank=True, null=True)
    firmada = models.BooleanField(default=False, db_index=True)
    firmada_en = models.DateTimeField(null=True, blank=True)
    firmada_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sanciones_firmadas",
    )

    class Meta:
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"{self.alumno} - {self.tipo} ({self.fecha})"


TIPOS_EVENTO = [
    ('EvaluaciÃ³n', 'EvaluaciÃ³n'),
    ('Entrega', 'Entrega'),
    ('Acto', 'Acto'),
    ('ReuniÃ³n', 'ReuniÃ³n'),
    ('Otro', 'Otro'),
]


class Evento(models.Model):
    titulo = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)

    # âœ… max_length grande (no varchar(2))
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
    ("informatica", "InformÃ¡tica"),
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
    firmada = models.BooleanField(default=False, db_index=True)
    firmada_en = models.DateTimeField(null=True, blank=True)
    firmada_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="asistencias_firmadas",
    )

    # âœ… default=timezone.now evita prompts de auto_now_add en tablas con filas existentes
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
            models.Index(fields=["alumno", "tipo_asistencia", "presente"]),
        ]

    def __str__(self):
        estado = "Ausente" if (not self.presente) else ("Tarde" if getattr(self, "tarde", False) else "Presente")
        return f"{self.alumno} - {self.fecha} - {self.tipo_asistencia} - {estado}"


class AlertaAcademica(models.Model):
    ESTADO_CHOICES = [
        ("activa", "Activa"),
        ("cerrada", "Cerrada"),
    ]

    alumno = models.ForeignKey(
        Alumno,
        on_delete=models.CASCADE,
        related_name="alertas_academicas",
        db_index=True,
    )
    materia = models.CharField(max_length=50, db_index=True)
    cuatrimestre = models.IntegerField(null=True, blank=True, db_index=True)
    severidad = models.IntegerField(db_index=True)
    riesgo_ponderado = models.DecimalField(max_digits=4, decimal_places=3, default=0)
    triggers = models.JSONField(default=dict, blank=True)
    ventana_desde = models.DateField(null=True, blank=True)
    ventana_hasta = models.DateField(null=True, blank=True)
    fecha_evento = models.DateField(default=timezone.localdate, db_index=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="activa", db_index=True)

    nota_disparadora = models.ForeignKey(
        "Nota",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alertas_disparadas",
    )
    creada_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alertas_creadas",
    )
    creada_en = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-creada_en", "-id"]
        indexes = [
            models.Index(fields=["alumno", "materia", "creada_en"]),
            models.Index(fields=["alumno", "materia", "cuatrimestre"]),
        ]

    def __str__(self):
        return f"Alerta N{self.severidad} - {self.alumno} - {self.materia}"


class AlertaInasistencia(models.Model):
    ESTADO_CHOICES = [
        ("activa", "Activa"),
        ("cerrada", "Cerrada"),
    ]
    MOTIVO_CHOICES = [
        ("AUSENCIAS_CONSECUTIVAS", "Ausencias consecutivas"),
        ("FALTAS_ACUMULADAS", "Faltas acumuladas"),
    ]

    alumno = models.ForeignKey(
        Alumno,
        on_delete=models.CASCADE,
        related_name="alertas_inasistencia",
        db_index=True,
    )
    curso = models.CharField(max_length=20, db_index=True)
    tipo_asistencia = models.CharField(max_length=20, default="clases", db_index=True)
    motivo = models.CharField(max_length=40, choices=MOTIVO_CHOICES, db_index=True)
    severidad = models.IntegerField(default=1, db_index=True)
    valor_actual = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    umbral = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="activa", db_index=True)
    fecha_evento = models.DateField(default=timezone.localdate, db_index=True)
    detalle = models.JSONField(default=dict, blank=True)
    asistencia_disparadora = models.ForeignKey(
        "Asistencia",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alertas_inasistencia_disparadas",
    )
    creada_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alertas_inasistencia_creadas",
    )
    creada_en = models.DateTimeField(auto_now_add=True, db_index=True)
    cerrada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creada_en", "-id"]
        indexes = [
            models.Index(fields=["alumno", "motivo", "estado"]),
            models.Index(fields=["curso", "estado", "creada_en"]),
        ]

    def __str__(self):
        return f"Inasistencia ({self.motivo}) - {self.alumno}"

# ------------------------------------------------------------
# Notificaciones (campana / inbox UI)
# ------------------------------------------------------------

class Notificacion(models.Model):
    TIPO_CHOICES = [
        ("nota", "Nota"),
        ("sancion", "SanciÃ³n"),
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
        indexes = [
            models.Index(fields=["destinatario", "leida", "creada_en"]),
            models.Index(fields=["destinatario", "creada_en"]),
        ]

    def __str__(self):
        return f"{self.tipo}: {self.titulo}"


