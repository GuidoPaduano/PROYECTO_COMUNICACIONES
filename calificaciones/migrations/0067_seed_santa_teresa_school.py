from django.db import migrations


SCHOOL = {
    "name": "Colegio Santa Teresa",
    "short_name": "Santa Teresa",
    "slug": "colegio-santa-teresa",
    "logo_url": "/imagenes/Santa%20teresa%20logo.png",
    "primary_color": "",
    "accent_color": "",
    "is_active": True,
}

COURSES = (
    ("1A", "1A"),
    ("1B", "1B"),
    ("2A", "2A"),
    ("2B", "2B"),
    ("3A", "3A"),
    ("3B", "3B"),
    ("4ECO", "4ECO"),
    ("4NAT", "4NAT"),
    ("5ECO", "5ECO"),
    ("5NAT", "5NAT"),
    ("6ECO", "6ECO"),
    ("6NAT", "6NAT"),
)


def seed_santa_teresa_school(apps, schema_editor):
    School = apps.get_model("calificaciones", "School")
    SchoolCourse = apps.get_model("calificaciones", "SchoolCourse")

    school, _ = School.objects.get_or_create(
        slug=SCHOOL["slug"],
        defaults=SCHOOL,
    )

    updates = {}
    for field, value in SCHOOL.items():
        if getattr(school, field) != value:
            updates[field] = value

    if updates:
        School.objects.filter(pk=school.pk).update(**updates)
        for field, value in updates.items():
            setattr(school, field, value)

    for index, (code, name) in enumerate(COURSES, start=1):
        SchoolCourse.objects.get_or_create(
            school=school,
            code=code,
            defaults={
                "name": name,
                "sort_order": index,
                "is_active": True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0066_schooladmin_and_admin_group"),
    ]

    operations = [
        migrations.RunPython(seed_santa_teresa_school, migrations.RunPython.noop),
    ]
