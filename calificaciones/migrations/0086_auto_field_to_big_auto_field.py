from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0085_fix_active_schools_public"),
    ]

    operations = [
        # Las migraciones 0080 y 0083 crearon estos modelos con AutoField explícito,
        # pero DEFAULT_AUTO_FIELD = BigAutoField en settings. Sincronizamos aquí.
        migrations.AlterField(
            model_name="ciclolectivo",
            name="id",
            field=models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
        ),
        migrations.AlterField(
            model_name="matricula",
            name="id",
            field=models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
        ),
        migrations.AlterField(
            model_name="profesorcursomateria",
            name="id",
            field=models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
        ),
        # Nota.materia: "Ciencias" → "Ciencias Naturales" y se agregó "Tecnología".
        # Solo afecta validación en memoria; no modifica la base de datos.
        migrations.AlterField(
            model_name="nota",
            name="materia",
            field=models.CharField(
                choices=[
                    ("Lengua", "Lengua"),
                    ("Matemática", "Matemática"),
                    ("Ciencias Naturales", "Ciencias Naturales"),
                    ("Historia", "Historia"),
                    ("Geografía", "Geografía"),
                    ("Inglés", "Inglés"),
                    ("Educación Física", "Educación Física"),
                    ("Música", "Música"),
                    ("Plástica", "Plástica"),
                    ("Catequesis", "Catequesis"),
                    ("Tecnología", "Tecnología"),
                    ("Informática", "Informática"),
                ],
                max_length=50,
            ),
        ),
    ]
