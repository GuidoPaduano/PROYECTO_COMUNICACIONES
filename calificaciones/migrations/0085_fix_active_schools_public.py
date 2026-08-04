from django.db import migrations


def set_active_schools_public(apps, schema_editor):
    School = apps.get_model("calificaciones", "School")
    School.objects.filter(is_active=True, is_public=False).update(is_public=True)


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0084_set_existing_schools_public"),
    ]

    operations = [
        migrations.RunPython(set_active_schools_public, migrations.RunPython.noop),
    ]
