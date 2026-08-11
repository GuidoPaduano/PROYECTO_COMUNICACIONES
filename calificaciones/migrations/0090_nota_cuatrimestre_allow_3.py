from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0089_add_nivel_to_schoolcourse"),
    ]

    operations = [
        migrations.AlterField(
            model_name="nota",
            name="cuatrimestre",
            field=models.IntegerField(choices=[(1, "1"), (2, "2"), (3, "3")]),
        ),
    ]
