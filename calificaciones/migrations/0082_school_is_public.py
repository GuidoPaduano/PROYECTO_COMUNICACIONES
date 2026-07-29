from django.db import migrations, models


def set_tecnova_public(apps, schema_editor):
    """Mark tecnova as public — the only school with DNS and CORS confirmed working."""
    School = apps.get_model("calificaciones", "School")
    School.objects.filter(slug="tecnova").update(is_public=True)


def unset_tecnova_public(apps, schema_editor):
    School = apps.get_model("calificaciones", "School")
    School.objects.filter(slug="tecnova").update(is_public=False)


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0081_normalize_materias"),
    ]

    operations = [
        migrations.AddField(
            model_name="school",
            name="is_public",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text=(
                    "Visible en el directorio público y habilitada para links de reset de contraseña. "
                    "Activar solo cuando DNS y CORS estén operativos."
                ),
            ),
        ),
        migrations.RunPython(set_tecnova_public, reverse_code=unset_tecnova_public),
    ]
