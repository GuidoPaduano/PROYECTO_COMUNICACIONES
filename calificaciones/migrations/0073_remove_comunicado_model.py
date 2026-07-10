from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0072_schoolmembership"),
    ]

    operations = [
        migrations.DeleteModel(
            name="Comunicado",
        ),
    ]
