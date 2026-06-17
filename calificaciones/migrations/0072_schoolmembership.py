from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0071_nota_version"),
    ]

    operations = [
        migrations.CreateModel(
            name="SchoolMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("assigned_at", models.DateTimeField(auto_now_add=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="user_memberships",
                        to="calificaciones.school",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="school_memberships",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Membresía institucional",
                "verbose_name_plural": "Membresías institucionales",
                "indexes": [
                    models.Index(fields=["school", "user"], name="calificacio_school__46d183_idx"),
                    models.Index(fields=["user"], name="calificacio_user_id_caac1d_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("school", "user"),
                        name="unique_school_user_membership",
                    ),
                ],
            },
        ),
    ]
