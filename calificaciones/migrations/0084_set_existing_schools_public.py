from django.db import migrations


def set_schools_public(apps, schema_editor):
    School = apps.get_model("calificaciones", "School")
    School.objects.filter(is_active=True).update(is_public=True)


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0083_profesor_curso_materia"),
    ]

    operations = [
        migrations.RunPython(set_schools_public, migrations.RunPython.noop),
    ]
