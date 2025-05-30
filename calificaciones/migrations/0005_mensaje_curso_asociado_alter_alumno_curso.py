# Generated by Django 5.1.7 on 2025-03-31 03:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('calificaciones', '0004_mensaje_delete_curso'),
    ]

    operations = [
        migrations.AddField(
            model_name='mensaje',
            name='curso_asociado',
            field=models.CharField(blank=True, max_length=10, null=True),
        ),
        migrations.AlterField(
            model_name='alumno',
            name='curso',
            field=models.CharField(choices=[('1A', '1°A'), ('1B', '1°B'), ('2A', '2°A'), ('2B', '2°B'), ('3A', '3°A'), ('3B', '3°B'), ('4ECO', '4° Economía'), ('4NAT', '4° Naturales'), ('5ECO', '5° Economía'), ('5NAT', '5° Naturales'), ('6ECO', '6° Economía'), ('6NAT', '6° Naturales')], max_length=10),
        ),
    ]
