from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0069_rename_calificacio_school__2ff736_idx_calificacio_school__3fbf7d_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="mensaje",
            name="client_request_id",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddConstraint(
            model_name="mensaje",
            constraint=models.UniqueConstraint(
                fields=("remitente", "client_request_id"),
                name="unique_mensaje_sender_request",
            ),
        ),
    ]
