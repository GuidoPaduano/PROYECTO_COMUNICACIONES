from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("calificaciones", "0067_seed_santa_teresa_school"),
    ]

    operations = [
        migrations.CreateModel(
            name="SchoolDeletionJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("school_name", models.CharField(blank=True, default="", max_length=150)),
                ("school_slug", models.SlugField(blank=True, default="", max_length=80)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pendiente"),
                            ("running", "En ejecucion"),
                            ("completed", "Completado"),
                            ("failed", "Fallido"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("error", models.TextField(blank=True, default="")),
                ("requested_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                (
                    "requested_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="school_deletion_jobs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="deletion_jobs",
                        to="calificaciones.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "Job de borrado de colegio",
                "verbose_name_plural": "Jobs de borrado de colegios",
                "ordering": ["-requested_at", "-id"],
                "indexes": [
                    models.Index(fields=["school", "status"], name="calificacio_school_31c49b_idx"),
                    models.Index(fields=["status", "requested_at"], name="calificacio_status_3f65bd_idx"),
                ],
            },
        ),
    ]
