from django.db import migrations


LEGACY_DEFAULT_SCHOOL_SLUG = "default"
TARGET_SCHOOL_SLUG = "escuela-itnova"


def rename_default_school_slug(apps, schema_editor):
    School = apps.get_model("calificaciones", "School")
    try:
        school = School.objects.filter(slug=LEGACY_DEFAULT_SCHOOL_SLUG).first()
        if school is None:
            return
        if School.objects.exclude(pk=school.pk).filter(slug=TARGET_SCHOOL_SLUG).exists():
            return
        school.slug = TARGET_SCHOOL_SLUG
        school.save(update_fields=["slug"])
    except Exception:
        return


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0048_rename_default_school_to_itnova"),
    ]

    operations = [
        migrations.RunPython(rename_default_school_slug, migrations.RunPython.noop),
    ]
