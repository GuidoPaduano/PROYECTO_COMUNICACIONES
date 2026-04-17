from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0063_evento_creado_por"),
    ]

    operations = [
        migrations.AddField(
            model_name="mensaje",
            name="alumno",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="mensajes",
                to="calificaciones.alumno",
            ),
        ),
    ]
