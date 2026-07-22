"""
Celery tasks para procesamiento asíncrono de alertas y notificaciones.
"""
from celery import shared_task


@shared_task(bind=True, max_retries=2, default_retry_delay=10)
def send_email_task(self, *, to_email: str, subject: str, text: str | None = None, html: str | None = None):
    try:
        from .resend_email import send_resend_email
        send_resend_email(to_email=to_email, subject=subject, text=text, html=html)
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=10)
def send_message_email_task(self, *, to_email: str, subject: str, content: str, actor_label: str = ""):
    try:
        from .resend_email import send_message_email
        send_message_email(to_email=to_email, subject=subject, content=content, actor_label=actor_label)
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def evaluar_alertas_inasistencia_task(self, alumno_ids, tipo_asistencia, actor_id=None):
    try:
        from django.contrib.auth import get_user_model
        from .alerts import evaluar_alertas_inasistencia_por_alumnos

        actor = get_user_model().objects.filter(pk=actor_id).first() if actor_id else None
        evaluar_alertas_inasistencia_por_alumnos(
            alumno_ids=alumno_ids,
            tipo_asistencia=tipo_asistencia,
            actor=actor,
        )
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def evaluar_alerta_inasistencia_task(self, alumno_id, asistencia_id, tipo_asistencia, actor_id=None):
    try:
        from django.contrib.auth import get_user_model
        from .models import Alumno, Asistencia
        from .alerts import evaluar_alerta_inasistencia

        alumno = Alumno.objects.get(pk=alumno_id)
        asistencia = Asistencia.objects.get(pk=asistencia_id)
        actor = get_user_model().objects.filter(pk=actor_id).first() if actor_id else None
        evaluar_alerta_inasistencia(
            alumno=alumno,
            tipo_asistencia=tipo_asistencia,
            actor=actor,
            asistencia=asistencia,
        )
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def evaluar_alerta_nota_task(self, nota_id, actor_id=None):
    try:
        from django.contrib.auth import get_user_model
        from .models._academico import Nota
        from .alerts import evaluar_alerta_nota

        nota = Nota.objects.get(pk=nota_id)
        actor = get_user_model().objects.filter(pk=actor_id).first() if actor_id else None
        evaluar_alerta_nota(nota=nota, actor=actor)
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def evaluar_alertas_notas_bulk_task(self, nota_ids, actor_id=None):
    try:
        from django.contrib.auth import get_user_model
        from .models._academico import Nota
        from .alerts import evaluar_alertas_notas_bulk

        notas = list(Nota.objects.filter(pk__in=nota_ids))
        actor = get_user_model().objects.filter(pk=actor_id).first() if actor_id else None
        evaluar_alertas_notas_bulk(notas=notas, actor=actor, send_email=False)
    except Exception as exc:
        raise self.retry(exc=exc)
