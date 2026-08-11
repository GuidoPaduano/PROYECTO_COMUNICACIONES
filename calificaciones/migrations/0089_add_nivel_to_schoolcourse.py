from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("calificaciones", "0088_add_nivel_to_alumno")]

    operations = [
        migrations.AddField(
            model_name="schoolcourse",
            name="nivel",
            field=models.CharField(
                max_length=20,
                choices=[("secundaria", "Secundaria"), ("primaria", "Primaria")],
                default="secundaria",
                db_index=True,
            ),
        ),
    ]
