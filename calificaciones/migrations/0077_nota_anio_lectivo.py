from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0076_nota_tipo_choices_nota_final"),
    ]

    operations = [
        migrations.AddField(
            model_name="nota",
            name="anio_lectivo",
            field=models.IntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.RemoveConstraint(
            model_name="nota",
            name="unique_nota_final_alumno_materia_cuatrimestre",
        ),
        migrations.AddConstraint(
            model_name="nota",
            constraint=models.UniqueConstraint(
                condition=models.Q(es_final=True, anio_lectivo__isnull=False),
                fields=["alumno", "materia", "cuatrimestre", "anio_lectivo"],
                name="unique_nota_final_alumno_materia_cuatrimestre_anio",
            ),
        ),
    ]
