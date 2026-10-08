from django.db.models import Exists, OuterRef
from .models import Mensaje


def with_reply_status(qs):
    # Virtual conversations are scoped to participants, school, student and course.
    # Coalesce lets unlinked legacy messages match each other without matching another student.
    from django.db.models.functions import Coalesce
    replies = Mensaje.objects.annotate(
        student_key=Coalesce('alumno_id', 0), course_key=Coalesce('school_course_id', 0),
    ).filter(
        school_id=OuterRef('school_id'), remitente_id=OuterRef('destinatario_id'),
        destinatario_id=OuterRef('remitente_id'), fecha_envio__gt=OuterRef('fecha_envio'),
        student_key=Coalesce(OuterRef('alumno_id'), 0),
        course_key=Coalesce(OuterRef('school_course_id'), 0),
    )
    return qs.annotate(recordatorio_respondido=Exists(replies))
