from django.db import migrations, models
import django.db.models.deletion
import django.db.models.expressions


def backfill_school_course_snapshot(apps, schema_editor):
    """
    Populate school_course_snapshot from each record's alumno.school_course.
    This is the best approximation available for existing records — it reflects
    the student's current course, not necessarily their course when the record
    was created. New records will capture the correct course at creation time
    via the model's save() method.
    """
    Nota = apps.get_model("calificaciones", "Nota")
    Asistencia = apps.get_model("calificaciones", "Asistencia")
    Sancion = apps.get_model("calificaciones", "Sancion")
    Alumno = apps.get_model("calificaciones", "Alumno")

    alumno_subq = Alumno.objects.filter(
        pk=django.db.models.expressions.OuterRef("alumno_id")
    ).values("school_course_id")[:1]

    for Model in (Nota, Asistencia, Sancion):
        Model.objects.filter(school_course_snapshot__isnull=True).update(
            school_course_snapshot=django.db.models.expressions.Subquery(alumno_subq)
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0079_fix_backfill_nota_anio_lectivo"),
    ]

    operations = [
        # ── CicloLectivo ──────────────────────────────────────────────────────
        migrations.CreateModel(
            name="CicloLectivo",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("anio", models.PositiveIntegerField()),
                ("nombre", models.CharField(blank=True, max_length=40)),
                ("activo", models.BooleanField(db_index=True, default=False)),
                ("fecha_inicio", models.DateField(blank=True, null=True)),
                ("fecha_fin", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ciclos_lectivos",
                        to="calificaciones.school",
                    ),
                ),
            ],
            options={"ordering": ["-anio"]},
        ),
        migrations.AddConstraint(
            model_name="ciclolectivo",
            constraint=models.UniqueConstraint(
                fields=["school", "anio"],
                name="unique_ciclo_lectivo_school_anio",
            ),
        ),

        # ── Matricula ─────────────────────────────────────────────────────────
        migrations.CreateModel(
            name="Matricula",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                (
                    "estado",
                    models.CharField(
                        choices=[
                            ("activa", "Activa"),
                            ("promovida", "Promovida"),
                            ("transferida", "Transferida"),
                            ("egresada", "Egresada"),
                            ("baja", "Baja"),
                        ],
                        db_index=True,
                        default="activa",
                        max_length=20,
                    ),
                ),
                ("fecha_desde", models.DateField(blank=True, null=True)),
                ("fecha_hasta", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "alumno",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="matriculas",
                        to="calificaciones.alumno",
                    ),
                ),
                (
                    "ciclo_lectivo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="matriculas",
                        to="calificaciones.ciclolectivo",
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="matriculas",
                        to="calificaciones.school",
                    ),
                ),
                (
                    "school_course",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="matriculas",
                        to="calificaciones.schoolcourse",
                    ),
                ),
            ],
            options={"ordering": ["-ciclo_lectivo__anio"]},
        ),
        migrations.AddConstraint(
            model_name="matricula",
            constraint=models.UniqueConstraint(
                fields=["ciclo_lectivo", "alumno"],
                name="unique_matricula_ciclo_alumno",
            ),
        ),

        # ── school_course_snapshot fields ─────────────────────────────────────
        migrations.AddField(
            model_name="nota",
            name="school_course_snapshot",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="notas_snapshot",
                to="calificaciones.schoolcourse",
            ),
        ),
        migrations.AddField(
            model_name="asistencia",
            name="school_course_snapshot",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="asistencias_snapshot",
                to="calificaciones.schoolcourse",
            ),
        ),
        migrations.AddField(
            model_name="sancion",
            name="school_course_snapshot",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="sanciones_snapshot",
                to="calificaciones.schoolcourse",
            ),
        ),

        # ── Backfill snapshots from current alumno.school_course ──────────────
        migrations.RunPython(backfill_school_course_snapshot, reverse_code=noop),
    ]
