from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator


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


HEX_COLOR_VALIDATOR = RegexValidator(
    regex=r"^#[0-9A-Fa-f]{6}$",
    message="Usa un color hexadecimal con formato #RRGGBB.",
)


class School(models.Model):
    name = models.CharField(max_length=150, unique=True)
    short_name = models.CharField(max_length=60, blank=True, default="")
    slug = models.SlugField(max_length=80, unique=True)
    logo_url = models.CharField(max_length=255, blank=True, default="")
    primary_color = models.CharField(max_length=7, blank=True, default="", validators=[HEX_COLOR_VALIDATOR])
    accent_color = models.CharField(max_length=7, blank=True, default="", validators=[HEX_COLOR_VALIDATOR])
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        verbose_name = "Colegio"
        verbose_name_plural = "Colegios"

    def __str__(self):
        return self.name


class SchoolCourse(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name="courses",
    )
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["school_id", "sort_order", "name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "code"],
                name="unique_school_course_code",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "is_active", "sort_order"]),
            models.Index(fields=["school", "code"]),
        ]
        verbose_name = "Curso por colegio"
        verbose_name_plural = "Cursos por colegio"

    def __str__(self):
        return f"{self.school} - {self.code}"


def resolve_school_course_for_value(*, school=None, curso=None):
    course_code = str(curso or "").strip().upper()
    if school is None or not course_code:
        return None
    try:
        return SchoolCourse.objects.filter(school=school, code__iexact=course_code).first()
    except Exception:
        return None


def sync_school_course_fields(instance, *, field_name: str = "school_course", school_attr: str = "school", code_attr: str = "curso"):
    school = getattr(instance, school_attr, None)
    school_course = getattr(instance, field_name, None)
    course_code = str(getattr(instance, code_attr, "") or "").strip().upper()

    if school_course is not None:
        if school is None:
            setattr(instance, school_attr, school_course.school)
            school = school_course.school

        if course_code and course_code != str(getattr(school_course, "code", "") or "").strip().upper():
            resolved = resolve_school_course_for_value(school=school or school_course.school, curso=course_code)
            setattr(instance, field_name, resolved)
            if resolved is not None:
                setattr(instance, code_attr, resolved.code)
            return

        if school is not None and getattr(school_course, "school_id", None) != getattr(school, "id", None):
            resolved = resolve_school_course_for_value(school=school, curso=course_code or getattr(school_course, "code", ""))
            setattr(instance, field_name, resolved)
            if resolved is not None:
                setattr(instance, code_attr, resolved.code)
            return

        setattr(instance, code_attr, getattr(school_course, "code", "") or course_code)
        return

    if school is None or not course_code:
        return

    resolved = resolve_school_course_for_value(school=school, curso=course_code)
    if resolved is not None:
        setattr(instance, field_name, resolved)
        setattr(instance, code_attr, resolved.code)


def sync_school_course_for_save(instance, kwargs, *, field_name: str = "school_course", school_attr: str = "school", code_attr: str = "curso"):
    update_fields = kwargs.get("update_fields")

    if update_fields is None:
        sync_school_course_fields(
            instance,
            field_name=field_name,
            school_attr=school_attr,
            code_attr=code_attr,
        )
        return

    tracked_fields = {field_name, school_attr, code_attr}
    update_fields_set = set(update_fields)
    if not update_fields_set.intersection(tracked_fields):
        return

    before_ids = {
        school_attr: getattr(instance, f"{school_attr}_id", None),
        field_name: getattr(instance, f"{field_name}_id", None),
    }
    before_values = {
        code_attr: getattr(instance, code_attr, None),
    }

    sync_school_course_fields(
        instance,
        field_name=field_name,
        school_attr=school_attr,
        code_attr=code_attr,
    )

    if getattr(instance, f"{school_attr}_id", None) != before_ids[school_attr]:
        update_fields_set.add(school_attr)
    if getattr(instance, f"{field_name}_id", None) != before_ids[field_name]:
        update_fields_set.add(field_name)
    if getattr(instance, code_attr, None) != before_values[code_attr]:
        update_fields_set.add(code_attr)

    kwargs["update_fields"] = list(update_fields_set)


def _should_enforce_school_integrity(instance, kwargs, tracked_fields):
    if getattr(instance._state, "adding", False):
        return True

    update_fields = kwargs.get("update_fields")
    if update_fields is None:
        return True

    return bool(set(update_fields).intersection(set(tracked_fields)))


def _mark_update_field(kwargs, field_name: str):
    update_fields = kwargs.get("update_fields")
    if update_fields is None:
        return
    update_fields_set = set(update_fields)
    update_fields_set.add(field_name)
    kwargs["update_fields"] = list(update_fields_set)


def _get_single_school_fallback():
    try:
        active = list(School.objects.filter(is_active=True).order_by("id")[:2])
        if len(active) == 1:
            return active[0]
        if active:
            return None

        schools = list(School.objects.order_by("id")[:2])
        if len(schools) == 1:
            return schools[0]
    except Exception:
        return None
    return None


def _collect_related_school_candidates(instance, related_fields):
    candidates = []
    seen = set()

    for field_name in related_fields or ():
        if not hasattr(instance, field_name):
            continue

        related = getattr(instance, field_name, None)
        if related is None:
            continue

        school = getattr(related, "school", None)
        if school is None:
            nested_alumno = getattr(related, "alumno", None)
            school = getattr(nested_alumno, "school", None)
        if school is None:
            continue

        school_id = getattr(school, "id", None)
        if school_id is None or school_id in seen:
            continue

        seen.add(school_id)
        candidates.append(school)

    return candidates


def ensure_school_for_save(instance, kwargs, *, related_fields=(), required_on_create: bool = True):
    tracked_fields = {"school", *set(related_fields or ())}
    if not _should_enforce_school_integrity(instance, kwargs, tracked_fields):
        return

    before_school_id = getattr(instance, "school_id", None)
    school = getattr(instance, "school", None)
    candidates = _collect_related_school_candidates(instance, related_fields)

    if school is None and len(candidates) == 1:
        setattr(instance, "school", candidates[0])
        school = candidates[0]

    if school is None and getattr(instance._state, "adding", False):
        fallback = _get_single_school_fallback()
        if fallback is not None:
            setattr(instance, "school", fallback)
            school = fallback

    after_school_id = getattr(instance, "school_id", None) or getattr(school, "id", None)
    if before_school_id != after_school_id:
        _mark_update_field(kwargs, "school")

    if after_school_id is not None:
        for candidate in candidates:
            candidate_id = getattr(candidate, "id", None)
            if candidate_id is not None and candidate_id != after_school_id:
                raise ValidationError("El colegio no coincide con la relacion asociada.")

    if required_on_create and getattr(instance._state, "adding", False):
        current_school = getattr(instance, "school", None)
        if getattr(instance, "school_id", None) is None and getattr(current_school, "id", None) is None:
            raise ValidationError("Debe indicarse el colegio para nuevas altas.")


def ensure_school_course_for_save(instance, kwargs, *, field_name: str = "school_course", school_attr: str = "school", code_attr: str = "curso"):
    tracked_fields = {field_name, school_attr, code_attr}
    if not _should_enforce_school_integrity(instance, kwargs, tracked_fields):
        return

    before_school_id = getattr(instance, f"{school_attr}_id", None)
    school = getattr(instance, school_attr, None)
    school_course = getattr(instance, field_name, None)

    if school is None and school_course is not None and getattr(school_course, "school", None) is not None:
        setattr(instance, school_attr, school_course.school)
        school = school_course.school

    if school is None and getattr(instance._state, "adding", False):
        fallback = _get_single_school_fallback()
        if fallback is not None:
            setattr(instance, school_attr, fallback)
            school = fallback

    if before_school_id != (getattr(instance, f"{school_attr}_id", None) or getattr(school, "id", None)):
        _mark_update_field(kwargs, school_attr)

    sync_school_course_for_save(
        instance,
        kwargs,
        field_name=field_name,
        school_attr=school_attr,
        code_attr=code_attr,
    )

    school = getattr(instance, school_attr, None)
    school_id = getattr(instance, f"{school_attr}_id", None) or getattr(school, "id", None)
    school_course = getattr(instance, field_name, None)
    course_code = str(getattr(instance, code_attr, "") or "").strip().upper()

    if getattr(instance._state, "adding", False) and school_id is None:
        raise ValidationError("Debe indicarse el colegio para nuevas altas.")

    if school_course is not None and school_id is not None and getattr(school_course, "school_id", None) != school_id:
        raise ValidationError("El curso asignado no pertenece al colegio indicado.")

    if school_id is not None and course_code and school_course is None:
        raise ValidationError(f"No existe un curso '{course_code}' para el colegio indicado.")


class Alumno(models.Model):
    # âœ… No achicamos curso a 2 porque tu DB ya tiene valores tipo 5NAT/4ECO, etc.
    CURSOS = [
        # Formato corto
        ('1A', '1A'), ('1B', '1B'),
        ('2A', '2A'), ('2B', '2B'),
        ('3A', '3A'), ('3B', '3B'),

        # Formato largo historico
        ('4ECO', '4ECO'), ('4NAT', '4NAT'),
        ('5ECO', '5ECO'), ('5NAT', '5NAT'),
        ('6ECO', '6ECO'), ('6NAT', '6NAT'),
    ]

    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100, default="", blank=True)
    id_alumno = models.CharField(max_length=20, db_index=True)  # ID/Legajo Ãºnico por colegio
    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name="alumnos",
    )
    school_course = models.ForeignKey(
        SchoolCourse,
        on_delete=models.PROTECT,
        related_name="alumnos",
    )

    # âœ… clave: max_length grande para NO romper al migrar
    curso = models.CharField(max_length=20, choices=CURSOS, db_index=True)

    padre = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="alumnos_como_padre")

    usuario = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="perfil_alumno")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["school", "id_alumno"],
                name="unique_alumno_school_legajo",
            ),
        ]

    def __str__(self):
        if self.apellido:
            return f"{self.apellido}, {self.nombre} ({self.curso})"
        return f"{self.nombre} ({self.curso})"

    def save(self, *args, **kwargs):
        ensure_school_course_for_save(self, kwargs)
        legajo = str(getattr(self, "id_alumno", "") or "").strip()
        school_id = getattr(self, "school_id", None)
        if legajo and school_id is not None:
            dupes = type(self).objects.filter(school_id=school_id, id_alumno__iexact=legajo)
            if self.pk:
                dupes = dupes.exclude(pk=self.pk)
            if dupes.exists():
                raise ValidationError({"id_alumno": "Ya existe un alumno con ese legajo en este colegio."})
        return super().save(*args, **kwargs)


class Nota(models.Model):
    MATERIAS = [
        ("Lengua", "Lengua"),
        ("Matem\u00e1tica", "Matem\u00e1tica"),
        ("Ciencias", "Ciencias"),
        ("Historia", "Historia"),
        ("Geograf\u00eda", "Geograf\u00eda"),
        ("Ingl\u00e9s", "Ingl\u00e9s"),
        ("Educaci\u00f3n F\u00edsica", "Educaci\u00f3n F\u00edsica"),
        ("M\u00fasica", "M\u00fasica"),
        ("Pl\u00e1stica", "Pl\u00e1stica"),
        ("Catequesis", "Catequesis"),
        ("Inform\u00e1tica", "Inform\u00e1tica"),
    ]

    TIPOS = [
        ("Examen", "Examen"),
        ("Trabajo Pr\u00e1ctico", "Trabajo Pr\u00e1ctico"),
        ("Participaci\u00f3n", "Participaci\u00f3n"),
        ("Tarea", "Tarea"),
    ]
    RESULTADO_CHOICES = [
        ("TEA", "Aprobado"),
        ("TEP", "Desaprobado"),
        ("TED", "Aplazado"),
    ]

    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name="notas",
    )
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
        indexes = [
            models.Index(fields=["alumno", "materia", "fecha"]),
        ]

    def __str__(self):
        return f"{self.alumno} - {self.materia}: {self.calificacion}"

    def save(self, *args, **kwargs):
        ensure_school_for_save(self, kwargs, related_fields=("alumno",))
        return super().save(*args, **kwargs)


class Mensaje(models.Model):
    REMITENTE_TIPOS = [
        ('Profesor', 'Profesor'),
        ('Preceptor', 'Preceptor'),
        ('Directivo', 'Directivo'),
    ]

    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name="mensajes",
    )
    school_course = models.ForeignKey(
        SchoolCourse,
        on_delete=models.PROTECT,
        related_name="mensajes",
        null=True,
        blank=True,
    )
    remitente = models.ForeignKey(User, on_delete=models.CASCADE, related_name="mensajes_enviados")
    destinatario = models.ForeignKey(User, on_delete=models.CASCADE, related_name="mensajes_recibidos")

    # max_length grande para codigos historicos
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

    def save(self, *args, **kwargs):
        ensure_school_course_for_save(self, kwargs)
        return super().save(*args, **kwargs)


class Comunicado(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name="comunicados",
    )
    school_course = models.ForeignKey(
        SchoolCourse,
        on_delete=models.PROTECT,
        related_name="comunicados",
        null=True,
        blank=True,
    )
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

    def save(self, *args, **kwargs):
        ensure_school_course_for_save(self, kwargs)
        return super().save(*args, **kwargs)


class Sancion(models.Model):
    TIPOS = [
        ('AmonestaciÃ³n', 'AmonestaciÃ³n'),
        ('Llamado de atenciÃ³n', 'Llamado de atenciÃ³n'),
        ('SuspensiÃ³n', 'SuspensiÃ³n'),
    ]

    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name="sanciones",
    )
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

    def save(self, *args, **kwargs):
        ensure_school_for_save(self, kwargs, related_fields=("alumno",))
        return super().save(*args, **kwargs)


TIPOS_EVENTO = [
    ('EvaluaciÃ³n', 'EvaluaciÃ³n'),
    ('Entrega', 'Entrega'),
    ('Acto', 'Acto'),
    ('ReuniÃ³n', 'ReuniÃ³n'),
    ('Otro', 'Otro'),
]


class Evento(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name="eventos",
    )
    school_course = models.ForeignKey(
        SchoolCourse,
        on_delete=models.PROTECT,
        related_name="eventos",
    )
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

    def save(self, *args, **kwargs):
        ensure_school_course_for_save(self, kwargs)
        return super().save(*args, **kwargs)


# =========================
# Asistencias
# =========================
TIPOS_ASISTENCIA = (
    ("clases", "Clases"),
    ("informatica", "InformÃ¡tica"),
    ("catequesis", "Catequesis"),
)


class Asistencia(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name="asistencias",
    )
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

    def save(self, *args, **kwargs):
        ensure_school_for_save(self, kwargs, related_fields=("alumno",))
        return super().save(*args, **kwargs)


class AlertaAcademica(models.Model):
    ESTADO_CHOICES = [
        ("activa", "Activa"),
        ("cerrada", "Cerrada"),
    ]

    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name="alertas_academicas",
    )
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

    def save(self, *args, **kwargs):
        ensure_school_for_save(self, kwargs, related_fields=("alumno", "nota_disparadora"))
        return super().save(*args, **kwargs)


class AlertaInasistencia(models.Model):
    ESTADO_CHOICES = [
        ("activa", "Activa"),
        ("cerrada", "Cerrada"),
    ]
    MOTIVO_CHOICES = [
        ("AUSENCIAS_CONSECUTIVAS", "Ausencias consecutivas"),
        ("FALTAS_ACUMULADAS", "Faltas acumuladas"),
    ]

    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name="alertas_inasistencias",
    )
    alumno = models.ForeignKey(
        Alumno,
        on_delete=models.CASCADE,
        related_name="alertas_inasistencia",
        db_index=True,
    )
    school_course = models.ForeignKey(
        SchoolCourse,
        on_delete=models.PROTECT,
        related_name="alertas_inasistencia",
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
            models.Index(fields=["school_course", "estado", "creada_en"], name="calificacio_school__3caeb5_idx"),
        ]

    def __str__(self):
        return f"Inasistencia ({self.motivo}) - {self.alumno}"

    def save(self, *args, **kwargs):
        ensure_school_for_save(self, kwargs, related_fields=("alumno", "asistencia_disparadora"))
        ensure_school_course_for_save(self, kwargs)
        return super().save(*args, **kwargs)

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

    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name="notificaciones",
    )
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

    def save(self, *args, **kwargs):
        ensure_school_for_save(self, kwargs)
        return super().save(*args, **kwargs)


