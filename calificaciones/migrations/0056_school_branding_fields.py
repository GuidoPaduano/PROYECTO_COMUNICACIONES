from django.db import migrations, models
import django.core.validators


def seed_default_school_branding(apps, schema_editor):
    School = apps.get_model("calificaciones", "School")
    school = (
        School.objects.filter(slug__iexact="escuela-itnova").first()
        or School.objects.filter(slug__iexact="default").first()
    )
    if school is None:
        return

    updates = {}
    if not (getattr(school, "short_name", "") or "").strip():
        updates["short_name"] = "Itnova"
    if not (getattr(school, "logo_url", "") or "").strip():
        updates["logo_url"] = "/imagenes/Logo%20Color.png"
    if not (getattr(school, "primary_color", "") or "").strip():
        updates["primary_color"] = "#0c1b3f"
    if not (getattr(school, "accent_color", "") or "").strip():
        updates["accent_color"] = "#4f46e5"

    if updates:
        for field_name, value in updates.items():
            setattr(school, field_name, value)
        school.save(update_fields=list(updates.keys()))


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0055_alertainasistencia_school_course"),
    ]

    operations = [
        migrations.AddField(
            model_name="school",
            name="accent_color",
            field=models.CharField(blank=True, default="", max_length=7, validators=[django.core.validators.RegexValidator(message="Usa un color hexadecimal con formato #RRGGBB.", regex="^#[0-9A-Fa-f]{6}$")]),
        ),
        migrations.AddField(
            model_name="school",
            name="logo_url",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="school",
            name="primary_color",
            field=models.CharField(blank=True, default="", max_length=7, validators=[django.core.validators.RegexValidator(message="Usa un color hexadecimal con formato #RRGGBB.", regex="^#[0-9A-Fa-f]{6}$")]),
        ),
        migrations.AddField(
            model_name="school",
            name="short_name",
            field=models.CharField(blank=True, default="", max_length=60),
        ),
        migrations.RunPython(seed_default_school_branding, migrations.RunPython.noop),
    ]
