from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0074_alerta_inasistencia_estado_vista"),
    ]

    operations = [
        migrations.AddField(
            model_name="nota",
            name="es_final",
            field=models.BooleanField(default=False, db_index=True),
        ),
        migrations.AddConstraint(
            model_name="nota",
            constraint=models.UniqueConstraint(
                condition=models.Q(es_final=True),
                fields=["alumno", "materia", "cuatrimestre"],
                name="unique_nota_final_alumno_materia_cuatrimestre",
            ),
        ),
    ]
