from django.db import migrations


LEGACY_COURSE_LABELS = {
    "1A": "1A",
    "1B": "1B",
    "2A": "2A",
    "2B": "2B",
    "3A": "3A",
    "3B": "3B",
    "4ECO": "4ECO",
    "4NAT": "4NAT",
    "5ECO": "5ECO",
    "5NAT": "5NAT",
    "6ECO": "6ECO",
    "6NAT": "6NAT",
}


def forwards(apps, schema_editor):
    School = apps.get_model("calificaciones", "School")
    SchoolCourse = apps.get_model("calificaciones", "SchoolCourse")
    Alumno = apps.get_model("calificaciones", "Alumno")

    try:
        PreceptorCurso = apps.get_model("calificaciones", "PreceptorCurso")
    except LookupError:
        PreceptorCurso = None

    try:
        ProfesorCurso = apps.get_model("calificaciones", "ProfesorCurso")
    except LookupError:
        ProfesorCurso = None

    for school in School.objects.all().order_by("id"):
        course_codes = {
            str(code).strip().upper()
            for code in Alumno.objects.filter(school=school).values_list("curso", flat=True)
            if str(code or "").strip()
        }

        if PreceptorCurso is not None:
            course_codes.update(
                str(code).strip().upper()
                for code in PreceptorCurso.objects.filter(school=school).values_list("curso", flat=True)
                if str(code or "").strip()
            )

        if ProfesorCurso is not None:
            course_codes.update(
                str(code).strip().upper()
                for code in ProfesorCurso.objects.filter(school=school).values_list("curso", flat=True)
                if str(code or "").strip()
            )

        if not course_codes and getattr(school, "slug", "") == "default":
            course_codes = set(LEGACY_COURSE_LABELS.keys())

        for index, code in enumerate(sorted(course_codes), start=1):
            defaults = {
                "name": LEGACY_COURSE_LABELS.get(code, code),
                "sort_order": index,
                "is_active": True,
            }
            obj, created = SchoolCourse.objects.get_or_create(
                school=school,
                code=code,
                defaults=defaults,
            )
            if created:
                continue
            update_fields = []
            if not getattr(obj, "name", ""):
                obj.name = defaults["name"]
                update_fields.append("name")
            if getattr(obj, "sort_order", 0) == 0:
                obj.sort_order = defaults["sort_order"]
                update_fields.append("sort_order")
            if update_fields:
                obj.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0044_schoolcourse"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
