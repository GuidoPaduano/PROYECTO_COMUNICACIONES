# calificaciones/migrations/0022_alter_asistencia_alumno_alter_asistencia_fecha.py
from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0021_preceptorcurso"),
    ]

    operations = [
        migrations.AlterField(
            model_name="asistencia",
            name="alumno",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="asistencias",
                to="calificaciones.alumno",
            ),
        ),
        migrations.AlterField(
            model_name="asistencia",
            name="fecha",
            field=models.DateField(
                default=timezone.localdate,
                db_index=True,
            ),
        ),
    ]
