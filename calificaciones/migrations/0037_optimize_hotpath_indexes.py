from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0036_alter_alertainasistencia_motivo"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="asistencia",
            index=models.Index(
                fields=["alumno", "tipo_asistencia", "presente"],
                name="calif_asis_tipo_pres_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="notificacion",
            index=models.Index(
                fields=["destinatario", "leida", "creada_en"],
                name="calif_notif_dlcr_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="notificacion",
            index=models.Index(
                fields=["destinatario", "creada_en"],
                name="calif_notif_dcr_idx",
            ),
        ),
    ]
