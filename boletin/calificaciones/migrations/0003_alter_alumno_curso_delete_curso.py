from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('calificaciones', '0002_curso_alumno_curso'),
    ]

    operations = [
        migrations.AlterField(
            model_name='alumno',
            name='curso',
            field=models.CharField(choices=[('1A', '1°A'), ('1B', '1°B'), ('2A', '2°A'), ('2B', '2°B'), ('3A', '3°A'), ('3B', '3°B'), ('4ECO', '4° ECO'), ('4NAT', '4° NAT'), ('5ECO', '5° ECO'), ('5NAT', '5° NAT'), ('6ECO', '6° ECO'), ('6NAT', '6° NAT')], default='1A', max_length=5),
        ),
    ]