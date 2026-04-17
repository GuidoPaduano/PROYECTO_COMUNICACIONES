from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("calificaciones", "0061_nota_calificacio_alumno__544098_idx"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "ALTER TABLE calificaciones_mensaje "
                "ADD COLUMN IF NOT EXISTS leido_en timestamp with time zone NULL;"
                "CREATE INDEX IF NOT EXISTS calificaciones_mensaje_leido_en_idx "
                "ON calificaciones_mensaje (leido_en);"
            ),
            reverse_sql=(
                "DROP INDEX IF EXISTS calificaciones_mensaje_leido_en_idx;"
                "ALTER TABLE calificaciones_mensaje "
                "DROP COLUMN IF EXISTS leido_en;"
            ),
        ),
    ]
