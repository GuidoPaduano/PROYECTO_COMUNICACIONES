from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0082_school_is_public"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ProfesorCursoMateria",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("materia", models.CharField(db_index=True, max_length=100)),
                ("asignado_en", models.DateTimeField(auto_now_add=True)),
                (
                    "profesor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="materias_asignadas",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="profesor_materia_asignaciones",
                        to="calificaciones.school",
                    ),
                ),
                (
                    "school_course",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="profesor_materia_asignaciones",
                        to="calificaciones.schoolcourse",
                    ),
                ),
            ],
            options={
                "verbose_name": "Materia asignada a profesor",
                "verbose_name_plural": "Materias asignadas a profesores",
            },
        ),
        migrations.AddIndex(
            model_name="profesorcursomateria",
            index=models.Index(fields=["profesor", "school_course"], name="calificaci_profeso_idx_pcm_pc"),
        ),
        migrations.AddIndex(
            model_name="profesorcursomateria",
            index=models.Index(fields=["school_course", "materia"], name="calificaci_school_idx_pcm_cm"),
        ),
        migrations.AlterUniqueTogether(
            name="profesorcursomateria",
            unique_together={("profesor", "school_course", "materia")},
        ),
    ]
