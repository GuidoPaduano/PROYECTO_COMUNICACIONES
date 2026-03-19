from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0039_nota_asistencia_firma_padre"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="sancion",
            name="firmada",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="sancion",
            name="firmada_en",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="sancion",
            name="firmada_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="sanciones_firmadas",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
