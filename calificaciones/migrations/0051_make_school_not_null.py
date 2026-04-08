from django.db import migrations, models
import django.db.models.deletion


DEFAULT_SCHOOL_SLUGS = ("escuela-itnova", "default")


def _get_default_school(School):
    for slug in DEFAULT_SCHOOL_SLUGS:
        school = School.objects.filter(slug__iexact=slug).first()
        if school is not None:
            return school
    return School.objects.order_by("id").first()


def _backfill_from_related(model, related_field: str):
    queryset = model.objects.filter(school__isnull=True).exclude(**{f"{related_field}__isnull": True})
    for obj in queryset.iterator():
        related = getattr(obj, related_field, None)
        school_id = getattr(related, "school_id", None)
        if school_id is not None:
            model.objects.filter(pk=obj.pk).update(school_id=school_id)


def backfill_missing_school(apps, schema_editor):
    School = apps.get_model("calificaciones", "School")
    Alumno = apps.get_model("calificaciones", "Alumno")
    Nota = apps.get_model("calificaciones", "Nota")
    Mensaje = apps.get_model("calificaciones", "Mensaje")
    Comunicado = apps.get_model("calificaciones", "Comunicado")
    Sancion = apps.get_model("calificaciones", "Sancion")
    Evento = apps.get_model("calificaciones", "Evento")
    Asistencia = apps.get_model("calificaciones", "Asistencia")
    AlertaAcademica = apps.get_model("calificaciones", "AlertaAcademica")
    AlertaInasistencia = apps.get_model("calificaciones", "AlertaInasistencia")
    Notificacion = apps.get_model("calificaciones", "Notificacion")
    PreceptorCurso = apps.get_model("calificaciones", "PreceptorCurso")
    ProfesorCurso = apps.get_model("calificaciones", "ProfesorCurso")

    default_school = _get_default_school(School)
    if default_school is None:
        return

    for alumno in Alumno.objects.filter(school__isnull=True).exclude(school_course__isnull=True).iterator():
        school_course = getattr(alumno, "school_course", None)
        school_id = getattr(school_course, "school_id", None)
        if school_id is not None:
            Alumno.objects.filter(pk=alumno.pk).update(school_id=school_id)
    Alumno.objects.filter(school__isnull=True).update(school_id=default_school.id)

    for model in (PreceptorCurso, ProfesorCurso):
        for asignacion in model.objects.filter(school__isnull=True).exclude(school_course__isnull=True).iterator():
            school_course = getattr(asignacion, "school_course", None)
            school_id = getattr(school_course, "school_id", None)
            if school_id is not None:
                model.objects.filter(pk=asignacion.pk).update(school_id=school_id)
        model.objects.filter(school__isnull=True).update(school_id=default_school.id)

    _backfill_from_related(Nota, "alumno")
    _backfill_from_related(Sancion, "alumno")
    _backfill_from_related(Asistencia, "alumno")
    _backfill_from_related(AlertaAcademica, "alumno")
    _backfill_from_related(AlertaInasistencia, "alumno")

    _backfill_from_related(AlertaAcademica, "nota_disparadora")
    _backfill_from_related(AlertaInasistencia, "asistencia_disparadora")

    for model in (Mensaje, Comunicado, Evento, Notificacion):
        model.objects.filter(school__isnull=True).update(school_id=default_school.id)

    for model in (Nota, Sancion, Asistencia, AlertaAcademica, AlertaInasistencia):
        model.objects.filter(school__isnull=True).update(school_id=default_school.id)


class Migration(migrations.Migration):

    dependencies = [
        ("calificaciones", "0050_alter_alumno_id_alumno_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_missing_school, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="alumno",
            name="school",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="alumnos", to="calificaciones.school"),
        ),
        migrations.AlterField(
            model_name="alertaacademica",
            name="school",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="alertas_academicas", to="calificaciones.school"),
        ),
        migrations.AlterField(
            model_name="alertainasistencia",
            name="school",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="alertas_inasistencias", to="calificaciones.school"),
        ),
        migrations.AlterField(
            model_name="asistencia",
            name="school",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="asistencias", to="calificaciones.school"),
        ),
        migrations.AlterField(
            model_name="comunicado",
            name="school",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="comunicados", to="calificaciones.school"),
        ),
        migrations.AlterField(
            model_name="evento",
            name="school",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="eventos", to="calificaciones.school"),
        ),
        migrations.AlterField(
            model_name="mensaje",
            name="school",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="mensajes", to="calificaciones.school"),
        ),
        migrations.AlterField(
            model_name="nota",
            name="school",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="notas", to="calificaciones.school"),
        ),
        migrations.AlterField(
            model_name="notificacion",
            name="school",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="notificaciones", to="calificaciones.school"),
        ),
        migrations.AlterField(
            model_name="preceptorcurso",
            name="school",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="preceptor_asignaciones", to="calificaciones.school"),
        ),
        migrations.AlterField(
            model_name="profesorcurso",
            name="school",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="profesor_asignaciones", to="calificaciones.school"),
        ),
        migrations.AlterField(
            model_name="sancion",
            name="school",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sanciones", to="calificaciones.school"),
        ),
    ]
