from django.db import migrations


def create_directivos_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name="Directivos")


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0040_sancion_firma_padre"),
    ]

    operations = [
        migrations.RunPython(create_directivos_group, migrations.RunPython.noop),
    ]
