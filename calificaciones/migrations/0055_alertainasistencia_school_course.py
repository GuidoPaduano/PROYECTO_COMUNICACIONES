from django.db import migrations, models


def backfill_alerta_inasistencia_school_course(apps, schema_editor):
    AlertaInasistencia = apps.get_model("calificaciones", "AlertaInasistencia")
    Alumno = apps.get_model("calificaciones", "Alumno")
    SchoolCourse = apps.get_model("calificaciones", "SchoolCourse")

    alumno_course_map = {
        alumno_id: school_course_id
        for alumno_id, school_course_id in Alumno.objects.values_list("id", "school_course_id")
        if school_course_id is not None
    }
    course_map = {
        (school_id, str(code or "").strip().upper()): course_id
        for school_id, code, course_id in SchoolCourse.objects.values_list("school_id", "code", "id")
    }

    missing = []
    for alerta in AlertaInasistencia.objects.all().only("id", "alumno_id", "school_id", "curso", "school_course_id").iterator():
        if getattr(alerta, "school_course_id", None) is not None:
            continue

        school_course_id = alumno_course_map.get(getattr(alerta, "alumno_id", None))
        if school_course_id is None:
            key = (getattr(alerta, "school_id", None), str(getattr(alerta, "curso", "") or "").strip().upper())
            school_course_id = course_map.get(key)
        if school_course_id is None:
            missing.append(getattr(alerta, "id", None))
            continue
        AlertaInasistencia.objects.filter(pk=alerta.pk).update(school_course_id=school_course_id)

    if missing:
        raise RuntimeError(f"No se pudo resolver school_course para alertas de inasistencia: {missing[:10]}")


class Migration(migrations.Migration):
    dependencies = [
        ("calificaciones", "0054_mensaje_comunicado_school_course"),
    ]

    operations = [
        migrations.AddField(
            model_name="alertainasistencia",
            name="school_course",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name="alertas_inasistencia",
                to="calificaciones.schoolcourse",
            ),
        ),
        migrations.RunPython(backfill_alerta_inasistencia_school_course, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="alertainasistencia",
            name="school_course",
            field=models.ForeignKey(
                on_delete=models.PROTECT,
                related_name="alertas_inasistencia",
                to="calificaciones.schoolcourse",
            ),
        ),
        migrations.AddIndex(
            model_name="alertainasistencia",
            index=models.Index(fields=["school_course", "estado", "creada_en"], name="calificacio_school__3caeb5_idx"),
        ),
    ]
