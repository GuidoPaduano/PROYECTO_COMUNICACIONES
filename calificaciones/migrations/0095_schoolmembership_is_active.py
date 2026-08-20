from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0094_documento_destinatario"),
    ]

    operations = [
        migrations.AddField(
            model_name="schoolmembership",
            name="is_active",
            field=models.BooleanField(default=True, db_index=True),
        ),
    ]
