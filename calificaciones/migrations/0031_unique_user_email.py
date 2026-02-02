from django.db import migrations


def dedupe_user_emails(apps, schema_editor):
    try:
        User = apps.get_model("auth", "User")
    except Exception:
        return

    # Evitar fallos si no existe el campo
    if not hasattr(User, "email"):
        return

    try:
        from django.db.models import Count
        from django.db.models.functions import Lower
    except Exception:
        return

    qs = User.objects.exclude(email__isnull=True).exclude(email__exact="")
    duplicates = (
        qs.annotate(email_lower=Lower("email"))
        .values("email_lower")
        .annotate(c=Count("id"))
        .filter(c__gt=1)
        .values_list("email_lower", flat=True)
    )

    for email_lower in list(duplicates):
        users = list(
            qs.annotate(email_lower=Lower("email"))
            .filter(email_lower=email_lower)
            .order_by("id")
        )
        if not users:
            continue

        # Preferir PRECEPTORTEST si existe para conservar el email
        preferred = None
        for u in users:
            if str(getattr(u, "username", "") or "").lower() == "preceptortest":
                preferred = u
                break

        keep = preferred or users[0]
        for u in users:
            if u.pk == keep.pk:
                continue
            u.email = ""
            u.save(update_fields=["email"])


def create_unique_email_index(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor not in ("postgresql", "sqlite"):
        return

    sql = (
        "CREATE UNIQUE INDEX IF NOT EXISTS auth_user_email_ci_uniq "
        "ON auth_user (LOWER(email)) "
        "WHERE email IS NOT NULL AND email <> ''"
    )
    try:
        schema_editor.execute(sql)
    except Exception:
        pass


def drop_unique_email_index(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor not in ("postgresql", "sqlite"):
        return

    sql = "DROP INDEX IF EXISTS auth_user_email_ci_uniq"
    try:
        schema_editor.execute(sql)
    except Exception:
        pass


class Migration(migrations.Migration):
    dependencies = [
        ("calificaciones", "0030_alter_notificacion_tipo_profesorcurso"),
    ]

    operations = [
        migrations.RunPython(dedupe_user_emails, reverse_code=migrations.RunPython.noop),
        migrations.RunPython(create_unique_email_index, reverse_code=drop_unique_email_index),
    ]
