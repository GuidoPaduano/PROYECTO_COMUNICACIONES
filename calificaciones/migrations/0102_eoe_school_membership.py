from django.db import migrations


def move_eoe_to_school(apps, schema_editor):
    Assignment = apps.get_model('calificaciones', 'PreceptorCurso')
    Membership = apps.get_model('calificaciones', 'SchoolMembership')
    alias = schema_editor.connection.alias
    assignments = Assignment.objects.using(alias).filter(preceptor__groups__name='EOE')
    for user_id, school_id in assignments.values_list('preceptor_id', 'school_id').distinct():
        Membership.objects.using(alias).get_or_create(user_id=user_id, school_id=school_id)
    assignments.delete()


class Migration(migrations.Migration):
    dependencies = [('calificaciones', '0101_ppi_document_read_receipts')]
    operations = [migrations.RunPython(move_eoe_to_school, migrations.RunPython.noop)]
