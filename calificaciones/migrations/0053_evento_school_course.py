from django.db import migrations, models


def backfill_evento_school_course(apps, schema_editor):
    Evento = apps.get_model("calificaciones", "Evento")
    SchoolCourse = apps.get_model("calificaciones", "SchoolCourse")

    course_map = {
        (school_id, str(code or "").strip().upper()): course_id
        for school_id, code, course_id in SchoolCourse.objects.values_list("school_id", "code", "id")
    }

    missing = []
    for evento in Evento.objects.all().only("id", "school_id", "curso", "school_course_id").iterator():
        if getattr(evento, "school_course_id", None) is not None:
            continue
        key = (getattr(evento, "school_id", None), str(getattr(evento, "curso", "") or "").strip().upper())
        school_course_id = course_map.get(key)
        if school_course_id is None:
            missing.append(getattr(evento, "id", None))
            continue
        Evento.objects.filter(pk=evento.pk).update(school_course_id=school_course_id)

    if missing:
        raise RuntimeError(f"No se pudo resolver school_course para eventos: {missing[:10]}")


class Migration(migrations.Migration):
    dependencies = [
        ("calificaciones", "0052_make_school_course_not_null"),
    ]

    operations = [
        migrations.AddField(
            model_name="evento",
            name="school_course",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name="eventos",
                to="calificaciones.schoolcourse",
            ),
        ),
        migrations.RunPython(backfill_evento_school_course, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="evento",
            name="school_course",
            field=models.ForeignKey(
                on_delete=models.PROTECT,
                related_name="eventos",
                to="calificaciones.schoolcourse",
            ),
        ),
    ]
