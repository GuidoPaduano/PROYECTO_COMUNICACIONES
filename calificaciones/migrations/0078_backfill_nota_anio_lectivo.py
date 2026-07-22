from django.db import migrations


def backfill_anio_lectivo(apps, schema_editor):
    Nota = apps.get_model("calificaciones", "Nota")
    notas = Nota.objects.filter(anio_lectivo__isnull=True).exclude(fecha__isnull=True)
    for nota in notas.iterator(chunk_size=500):
        nota.anio_lectivo = nota.fecha.year
    Nota.objects.bulk_update(notas, ["anio_lectivo"], batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0077_nota_anio_lectivo"),
    ]

    operations = [
        migrations.RunPython(backfill_anio_lectivo, migrations.RunPython.noop),
    ]
