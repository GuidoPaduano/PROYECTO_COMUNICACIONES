from django.db import migrations


DEFAULT_SCHOOL_SLUG = "default"
DEFAULT_SCHOOL_NAME = "Escuela Itnova"


def rename_default_school(apps, schema_editor):
    School = apps.get_model("calificaciones", "School")
    try:
        school = School.objects.filter(slug=DEFAULT_SCHOOL_SLUG).first()
        if school is None:
            return
        if getattr(school, "name", "") != DEFAULT_SCHOOL_NAME:
            school.name = DEFAULT_SCHOOL_NAME
            school.save(update_fields=["name"])
    except Exception:
        return


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0047_backfill_schoolcourse_links"),
    ]

    operations = [
        migrations.RunPython(rename_default_school, migrations.RunPython.noop),
    ]
