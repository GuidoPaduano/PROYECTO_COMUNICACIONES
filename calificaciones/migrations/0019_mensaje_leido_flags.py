# calificaciones/migrations/0019_mensaje_leido_flags.py
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ("calificaciones", "0018_alter_mensaje_options_mensaje_reply_to_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="mensaje",
            name="leido",
            field=models.BooleanField(default=False, db_index=True),
        ),
        migrations.AddField(
            model_name="mensaje",
            name="leido_en",
            field=models.DateTimeField(null=True, blank=True, db_index=True),
        ),
    ]
