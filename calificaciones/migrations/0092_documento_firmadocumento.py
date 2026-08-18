from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import calificaciones.models._documentos


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0091_nota_tipo_remove_choices"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Documento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titulo", models.CharField(max_length=255)),
                ("descripcion", models.TextField(blank=True, default="")),
                ("tipo", models.CharField(
                    choices=[
                        ("autorizacion", "Autorización"),
                        ("normas", "Normas de convivencia"),
                        ("circular", "Circular"),
                        ("otro", "Otro"),
                    ],
                    default="otro",
                    max_length=20,
                )),
                ("archivo", models.FileField(upload_to=calificaciones.models._documentos._documento_upload_path)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("requiere_firma", models.BooleanField(default=True)),
                ("school", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="documentos",
                    to="calificaciones.school",
                )),
                ("subido_por", models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="documentos_subidos",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["-creado_en"]},
        ),
        migrations.CreateModel(
            name="FirmaDocumento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fecha_firma", models.DateTimeField(auto_now_add=True)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("documento", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="firmas",
                    to="calificaciones.documento",
                )),
                ("usuario", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="firmas_documentos",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "ordering": ["fecha_firma"],
                "unique_together": {("documento", "usuario")},
            },
        ),
    ]
