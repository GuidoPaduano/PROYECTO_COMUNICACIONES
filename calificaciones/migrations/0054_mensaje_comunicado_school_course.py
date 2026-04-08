from django.db import migrations, models


def _course_map(apps):
    SchoolCourse = apps.get_model("calificaciones", "SchoolCourse")
    return {
        (school_id, str(code or "").strip().upper()): course_id
        for school_id, code, course_id in SchoolCourse.objects.values_list("school_id", "code", "id")
    }


def _backfill_model(apps, model_name: str):
    model = apps.get_model("calificaciones", model_name)
    course_map = _course_map(apps)

    for row in model.objects.all().only("id", "school_id", "curso", "school_course_id").iterator():
        if getattr(row, "school_course_id", None) is not None:
            continue
        course_code = str(getattr(row, "curso", "") or "").strip().upper()
        if not course_code:
            continue
        school_course_id = course_map.get((getattr(row, "school_id", None), course_code))
        if school_course_id is None:
            continue
        model.objects.filter(pk=row.pk).update(school_course_id=school_course_id)


def forwards(apps, schema_editor):
    _backfill_model(apps, "Mensaje")
    _backfill_model(apps, "Comunicado")


class Migration(migrations.Migration):
    dependencies = [
        ("calificaciones", "0053_evento_school_course"),
    ]

    operations = [
        migrations.AddField(
            model_name="mensaje",
            name="school_course",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name="mensajes",
                to="calificaciones.schoolcourse",
            ),
        ),
        migrations.AddField(
            model_name="comunicado",
            name="school_course",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name="comunicados",
                to="calificaciones.schoolcourse",
            ),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
