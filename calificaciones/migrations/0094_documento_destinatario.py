from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0093_documento_school_course"),
    ]

    operations = [
        migrations.AddField(
            model_name="documento",
            name="destinatario",
            field=models.CharField(
                choices=[
                    ("todos", "Padres y alumnos"),
                    ("padres", "Solo padres"),
                    ("alumnos", "Solo alumnos"),
                ],
                default="todos",
                max_length=20,
            ),
        ),
    ]
