from django.db import migrations


DEFAULT_SCHOOL_SLUG = "default"
DEFAULT_SCHOOL_NAME = "Colegio Principal"


def backfill_default_school(apps, schema_editor):
    School = apps.get_model("calificaciones", "School")
    default_school, _ = School.objects.get_or_create(
        slug=DEFAULT_SCHOOL_SLUG,
        defaults={
            "name": DEFAULT_SCHOOL_NAME,
            "is_active": True,
        },
    )

    model_names = [
        "Alumno",
        "Nota",
        "Mensaje",
        "Comunicado",
        "Sancion",
        "Evento",
        "Asistencia",
        "AlertaAcademica",
        "AlertaInasistencia",
        "Notificacion",
        "PreceptorCurso",
        "ProfesorCurso",
    ]

    for model_name in model_names:
        model = apps.get_model("calificaciones", model_name)
        model.objects.filter(school__isnull=True).update(school=default_school)


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0042_school_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_default_school, migrations.RunPython.noop),
    ]
