from django.db import migrations


def create_eoe_group(apps, schema_editor):
    apps.get_model("auth", "Group").objects.using(schema_editor.connection.alias).get_or_create(name="EOE")


class Migration(migrations.Migration):
    dependencies = [("calificaciones", "0095_schoolmembership_is_active")]
    operations = [migrations.RunPython(create_eoe_group, migrations.RunPython.noop)]
