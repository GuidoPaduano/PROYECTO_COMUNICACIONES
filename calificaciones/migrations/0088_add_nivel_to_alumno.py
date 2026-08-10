from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0087_add_alumno_school_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="alumno",
            name="nivel",
            field=models.CharField(
                choices=[("secundaria", "Secundaria"), ("primaria", "Primaria")],
                default="secundaria",
                db_index=True,
                max_length=20,
            ),
        ),
    ]
