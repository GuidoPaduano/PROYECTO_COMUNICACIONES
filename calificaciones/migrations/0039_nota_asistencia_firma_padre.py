from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0038_optimize_mensajes_indexes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="asistencia",
            name="firmada",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="asistencia",
            name="firmada_en",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="asistencia",
            name="firmada_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="asistencias_firmadas",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="nota",
            name="firmada",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="nota",
            name="firmada_en",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="nota",
            name="firmada_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="notas_firmadas",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
