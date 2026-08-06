from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0086_auto_field_to_big_auto_field"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="alumno",
            index=models.Index(
                fields=["school", "nombre"],
                name="alumno_school_nombre_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="alumno",
            index=models.Index(
                fields=["school", "school_course"],
                name="alumno_school_course_idx",
            ),
        ),
    ]
