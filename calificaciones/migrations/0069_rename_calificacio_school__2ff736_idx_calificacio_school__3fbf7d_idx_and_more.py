from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0068_schooldeletionjob"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="schooladmin",
            new_name="calificacio_school__3fbf7d_idx",
            old_name="calificacio_school__2ff736_idx",
        ),
        migrations.RenameIndex(
            model_name="schooladmin",
            new_name="calificacio_admin_i_c50593_idx",
            old_name="calificacio_admin_i_5c6535_idx",
        ),
        migrations.RenameIndex(
            model_name="schooldeletionjob",
            new_name="calificacio_school__88cca4_idx",
            old_name="calificacio_school_31c49b_idx",
        ),
        migrations.RenameIndex(
            model_name="schooldeletionjob",
            new_name="calificacio_status_194fa7_idx",
            old_name="calificacio_status_3f65bd_idx",
        ),
    ]
