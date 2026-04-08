from django.db import migrations


OLD_PRIMARY = "#0c1b3f"
OLD_ACCENT = "#4f46e5"
NEW_PRIMARY = "#2563EB"
NEW_ACCENT = "#1D4ED8"


def forwards(apps, schema_editor):
    School = apps.get_model("calificaciones", "School")

    for school in School.objects.all().only("id", "primary_color", "accent_color"):
        updates = {}
        primary = (getattr(school, "primary_color", "") or "").strip()
        accent = (getattr(school, "accent_color", "") or "").strip()

        if not primary or primary.lower() == OLD_PRIMARY:
            updates["primary_color"] = NEW_PRIMARY
        if not accent or accent.lower() == OLD_ACCENT:
            updates["accent_color"] = NEW_ACCENT

        if updates:
            School.objects.filter(pk=school.pk).update(**updates)


class Migration(migrations.Migration):
    dependencies = [
        ("calificaciones", "0056_school_branding_fields"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
