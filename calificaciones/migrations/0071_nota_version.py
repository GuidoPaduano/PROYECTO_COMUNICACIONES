from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0070_mensaje_client_request_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="nota",
            name="version",
            field=models.PositiveIntegerField(default=1),
        ),
    ]
