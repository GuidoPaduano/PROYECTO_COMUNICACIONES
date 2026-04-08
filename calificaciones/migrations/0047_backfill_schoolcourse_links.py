from django.db import migrations


def _course_map_for_school(SchoolCourse, cache, school_id):
    if not school_id:
        return {}
    if school_id not in cache:
        cache[school_id] = {
            str(code or "").strip().upper(): course_id
            for course_id, code in SchoolCourse.objects.filter(school_id=school_id).values_list("id", "code")
            if str(code or "").strip()
        }
    return cache[school_id]


def _backfill_model_school_course(model, SchoolCourse):
    cache = {}
    pending = []

    qs = model.objects.filter(school_course__isnull=True, school__isnull=False).order_by("id")
    for obj in qs.iterator(chunk_size=500):
        course_code = str(getattr(obj, "curso", "") or "").strip().upper()
        if not course_code:
            continue

        course_id = _course_map_for_school(SchoolCourse, cache, getattr(obj, "school_id", None)).get(course_code)
        if not course_id:
            continue

        obj.school_course_id = course_id
        pending.append(obj)

        if len(pending) >= 500:
            model.objects.bulk_update(pending, ["school_course"], batch_size=500)
            pending = []

    if pending:
        model.objects.bulk_update(pending, ["school_course"], batch_size=500)


def forwards(apps, schema_editor):
    SchoolCourse = apps.get_model("calificaciones", "SchoolCourse")
    Alumno = apps.get_model("calificaciones", "Alumno")
    PreceptorCurso = apps.get_model("calificaciones", "PreceptorCurso")
    ProfesorCurso = apps.get_model("calificaciones", "ProfesorCurso")

    _backfill_model_school_course(Alumno, SchoolCourse)
    _backfill_model_school_course(PreceptorCurso, SchoolCourse)
    _backfill_model_school_course(ProfesorCurso, SchoolCourse)


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0046_alter_preceptorcurso_options_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
