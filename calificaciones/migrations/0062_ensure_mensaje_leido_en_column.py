from django.db import migrations, models


TABLE_NAME = "calificaciones_mensaje"
COLUMN_NAME = "leido_en"
INDEX_NAME = "calificaciones_mensaje_leido_en_idx"


def _column_exists(schema_editor):
    with schema_editor.connection.cursor() as cursor:
        columns = schema_editor.connection.introspection.get_table_description(cursor, TABLE_NAME)
    return any(column.name == COLUMN_NAME for column in columns)


def _index_exists(schema_editor):
    with schema_editor.connection.cursor() as cursor:
        constraints = schema_editor.connection.introspection.get_constraints(cursor, TABLE_NAME)
    return INDEX_NAME in constraints


def ensure_leido_en_column(apps, schema_editor):
    Mensaje = apps.get_model("calificaciones", "Mensaje")
    if not _column_exists(schema_editor):
        field = models.DateTimeField(null=True, blank=True)
        field.set_attributes_from_name(COLUMN_NAME)
        schema_editor.add_field(Mensaje, field)

    if not _index_exists(schema_editor):
        schema_editor.execute(f"CREATE INDEX {INDEX_NAME} ON {TABLE_NAME} ({COLUMN_NAME})")


def reverse_leido_en_column(apps, schema_editor):
    if _index_exists(schema_editor):
        schema_editor.execute(f"DROP INDEX {INDEX_NAME}")
    if _column_exists(schema_editor):
        Mensaje = apps.get_model("calificaciones", "Mensaje")
        field = models.DateTimeField(null=True, blank=True)
        field.set_attributes_from_name(COLUMN_NAME)
        schema_editor.remove_field(Mensaje, field)


class Migration(migrations.Migration):
    dependencies = [
        ("calificaciones", "0061_nota_calificacio_alumno__544098_idx"),
    ]

    operations = [
        migrations.RunPython(ensure_leido_en_column, reverse_leido_en_column),
    ]
