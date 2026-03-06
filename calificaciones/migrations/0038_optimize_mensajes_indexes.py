from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0037_optimize_hotpath_indexes"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="mensaje",
            index=models.Index(
                fields=["destinatario", "leido", "fecha_envio"],
                name="calif_msg_dlf_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="mensaje",
            index=models.Index(
                fields=["destinatario", "fecha_envio"],
                name="calif_msg_df_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="mensaje",
            index=models.Index(
                fields=["remitente", "fecha_envio"],
                name="calif_msg_rf_idx",
            ),
        ),
    ]
