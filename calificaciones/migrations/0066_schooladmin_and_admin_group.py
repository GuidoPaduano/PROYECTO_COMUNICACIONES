from django.db import migrations, models
import django.db.models.deletion


def create_admin_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name="Administradores")


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0065_mensaje_leido_en"),
    ]

    operations = [
        migrations.CreateModel(
            name="SchoolAdmin",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("assigned_at", models.DateTimeField(auto_now_add=True)),
                ("admin", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="school_admin_assignments", to="auth.user")),
                ("school", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="school_admin_assignments", to="calificaciones.school")),
            ],
            options={
                "verbose_name": "Administrador de colegio",
                "verbose_name_plural": "Administradores de colegio",
                "indexes": [models.Index(fields=["school", "admin"], name="calificacio_school__2ff736_idx"), models.Index(fields=["admin"], name="calificacio_admin_i_5c6535_idx")],
                "unique_together": {("school", "admin")},
            },
        ),
        migrations.RunPython(create_admin_group, migrations.RunPython.noop),
    ]
