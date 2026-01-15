from django.db import migrations


def forwards(apps, schema_editor):
    Alumno = apps.get_model("calificaciones", "Alumno")
    User = apps.get_model("auth", "User")
    Group = apps.get_model("auth", "Group")

    # Tomamos grupo "Alumnos" si existe
    try:
        alumnos_group = Group.objects.get(name="Alumnos")
        users_alumnos = User.objects.filter(groups=alumnos_group)
    except Exception:
        users_alumnos = User.objects.all()

    # Heurística 1: match por username == id_alumno
    for u in users_alumnos.iterator():
        username = (getattr(u, "username", "") or "").strip()
        if not username:
            continue

        try:
            a = Alumno.objects.filter(id_alumno=username, user__isnull=True).first()
        except Exception:
            a = None

        if a:
            a.user = u
            a.save(update_fields=["user"])


def backwards(apps, schema_editor):
    Alumno = apps.get_model("calificaciones", "Alumno")
    Alumno.objects.update(user=None)


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0023_alter_alumno_usuario"),  # <-- cambialo por el nombre real anterior
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
