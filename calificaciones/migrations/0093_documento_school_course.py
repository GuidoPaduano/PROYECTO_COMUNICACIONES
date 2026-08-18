from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0092_documento_firmadocumento"),
    ]

    operations = [
        migrations.AddField(
            model_name="documento",
            name="school_course",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="documentos",
                to="calificaciones.schoolcourse",
            ),
        ),
    ]
