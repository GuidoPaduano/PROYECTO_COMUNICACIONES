from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0075_nota_es_final"),
    ]

    operations = [
        migrations.AlterField(
            model_name="nota",
            name="tipo",
            field=models.CharField(
                max_length=50,
                choices=[
                    ("Examen", "Examen"),
                    ("Trabajo Práctico", "Trabajo Práctico"),
                    ("Participación", "Participación"),
                    ("Tarea", "Tarea"),
                    ("Nota Final", "Nota Final"),
                ],
            ),
        ),
    ]
