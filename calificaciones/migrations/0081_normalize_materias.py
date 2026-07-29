from django.db import migrations


ALIAS_MAP = {
    "Ciencias": "Ciencias Naturales",
}


def normalize_materias(apps, schema_editor):
    Nota = apps.get_model("calificaciones", "Nota")
    for old, new in ALIAS_MAP.items():
        Nota.objects.filter(materia=old).update(materia=new)


def denormalize_materias(apps, schema_editor):
    Nota = apps.get_model("calificaciones", "Nota")
    for old, new in ALIAS_MAP.items():
        Nota.objects.filter(materia=new).update(materia=old)


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0080_ciclo_lectivo_matricula_snapshots"),
    ]

    operations = [
        migrations.RunPython(normalize_materias, reverse_code=denormalize_materias),
    ]
