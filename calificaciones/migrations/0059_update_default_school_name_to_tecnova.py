from django.db import migrations


TARGET_SLUGS = ("escuela-itnova", "default")


def rename_default_school_to_tecnova(apps, schema_editor):
    School = apps.get_model("calificaciones", "School")

    school = (
        School.objects.filter(slug__in=TARGET_SLUGS).order_by("id").first()
        or School.objects.filter(name__iexact="Escuela Itnova").order_by("id").first()
        or School.objects.filter(short_name__iexact="Itnova").order_by("id").first()
    )
    if school is None:
        return

    updates = {}
    if getattr(school, "name", "") != "Escuela Tecnova":
        updates["name"] = "Escuela Tecnova"
    if getattr(school, "short_name", "") != "Tecnova":
        updates["short_name"] = "Tecnova"

    if updates:
        for field_name, value in updates.items():
            setattr(school, field_name, value)
        school.save(update_fields=list(updates.keys()))


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0058_update_default_school_primary_to_navy"),
    ]

    operations = [
        migrations.RunPython(rename_default_school_to_tecnova, migrations.RunPython.noop),
    ]
