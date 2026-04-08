from django.db import migrations


OLD_SLUGS = ("escuela-itnova", "default")
NEW_SLUG = "escuela-tecnova"


def rename_default_school_slug_to_tecnova(apps, schema_editor):
    School = apps.get_model("calificaciones", "School")

    school = (
        School.objects.filter(slug__in=OLD_SLUGS).order_by("id").first()
        or School.objects.filter(name__iexact="Escuela Tecnova").order_by("id").first()
        or School.objects.filter(short_name__iexact="Tecnova").order_by("id").first()
    )
    if school is None:
        return

    if getattr(school, "slug", "") != NEW_SLUG:
        school.slug = NEW_SLUG
        school.save(update_fields=["slug"])


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0059_update_default_school_name_to_tecnova"),
    ]

    operations = [
        migrations.RunPython(
            rename_default_school_slug_to_tecnova,
            migrations.RunPython.noop,
        ),
    ]
