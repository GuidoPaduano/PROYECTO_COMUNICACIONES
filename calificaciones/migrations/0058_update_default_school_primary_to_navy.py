from django.db import migrations


OLD_PRIMARY = "#2563eb"
NEW_PRIMARY = "#0C1B3F"


def forwards(apps, schema_editor):
    School = apps.get_model("calificaciones", "School")

    for school in School.objects.all().only("id", "primary_color"):
        primary = (getattr(school, "primary_color", "") or "").strip()
        if primary and primary.lower() != OLD_PRIMARY:
            continue
        School.objects.filter(pk=school.pk).update(primary_color=NEW_PRIMARY)


class Migration(migrations.Migration):
    dependencies = [
        ("calificaciones", "0057_update_default_school_branding_to_blue"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
