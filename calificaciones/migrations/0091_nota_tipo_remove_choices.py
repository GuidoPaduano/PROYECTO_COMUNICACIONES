from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0090_nota_cuatrimestre_allow_3"),
    ]

    operations = [
        migrations.AlterField(
            model_name="nota",
            name="tipo",
            field=models.CharField(max_length=50),
        ),
    ]
