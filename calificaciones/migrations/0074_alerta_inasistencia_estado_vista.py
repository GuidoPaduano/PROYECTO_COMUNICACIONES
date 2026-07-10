from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0073_remove_comunicado_model"),
    ]

    operations = [
        migrations.AlterField(
            model_name="alertainasistencia",
            name="estado",
            field=models.CharField(
                choices=[
                    ("activa", "Activa"),
                    ("cerrada", "Cerrada"),
                    ("vista", "Vista"),
                ],
                db_index=True,
                default="activa",
                max_length=20,
            ),
        ),
    ]
