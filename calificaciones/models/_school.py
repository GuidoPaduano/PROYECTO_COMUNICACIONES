from django.contrib.auth.models import User
from django.db import models

from ._validators import HEX_COLOR_VALIDATOR


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


class SchoolDeletionJob(models.Model):
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pendiente"),
        (STATUS_RUNNING, "En ejecucion"),
        (STATUS_COMPLETED, "Completado"),
        (STATUS_FAILED, "Fallido"),
    ]

    school = models.ForeignKey(
        School,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deletion_jobs",
    )
    requested_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="school_deletion_jobs",
    )
    school_name = models.CharField(max_length=150, blank=True, default="")
    school_slug = models.SlugField(max_length=80, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    error = models.TextField(blank=True, default="")
    requested_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-requested_at", "-id"]
        indexes = [
            models.Index(fields=["school", "status"]),
            models.Index(fields=["status", "requested_at"]),
        ]
        verbose_name = "Job de borrado de colegio"
        verbose_name_plural = "Jobs de borrado de colegios"

    def __str__(self):
        target = self.school_name or self.school_slug or f"school:{self.school_id or 'n/a'}"
        return f"{target} [{self.status}]"


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
