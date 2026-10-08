from django.db import migrations


def create_group(apps, schema_editor):
    apps.get_model("auth", "Group").objects.using(schema_editor.connection.alias).get_or_create(name="Integracion")


class Migration(migrations.Migration):
    dependencies = [("calificaciones", "0098_ppi_documents")]
    operations = [migrations.RunPython(create_group, migrations.RunPython.noop)]
