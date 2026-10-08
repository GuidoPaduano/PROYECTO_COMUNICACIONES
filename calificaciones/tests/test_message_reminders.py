from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from calificaciones.models import Mensaje, Notificacion, School, SchoolCourse, Alumno
from calificaciones.models_preceptores import SchoolMembership
from calificaciones.message_reminders import with_reply_status


@override_settings(SECURE_SSL_REDIRECT=False, EMAIL_NOTIFICATIONS_ENABLED=False)
class MessageReminderTests(TestCase):
    def setUp(self):
        cache.clear()
        self.school = School.objects.create(name='Reminder', slug='reminder')
        self.course = SchoolCourse.objects.create(school=self.school, code='1A', name='1A')
        User = get_user_model()
        self.sender = User.objects.create_user(username='preceptor_reminder')
        self.recipient = User.objects.create_user(username='family_reminder')
        self.stranger = User.objects.create_user(username='stranger_reminder')
        self.sender.groups.add(Group.objects.get_or_create(name='Preceptores')[0])
        for user in [self.sender, self.recipient, self.stranger]:
            SchoolMembership.objects.create(school=self.school, user=user)
        self.student = Alumno.objects.create(school=self.school, school_course=self.course, curso='1A', nombre='Ana', id_alumno='REM1')
        self.message = Mensaje.objects.create(school=self.school, school_course=self.course, alumno=self.student, remitente=self.sender, destinatario=self.recipient, asunto='Citación', contenido='Solicitud de reunión')
        self.client = APIClient()
        self.client.force_authenticate(self.sender)
        self.url = f'/api/mensajes/{self.message.id}/recordatorio'

    def post(self, action='recordar'):
        return self.client.post(self.url, {'accion':action}, format='json', HTTP_X_SCHOOL=self.school.slug)

    def test_immediate_reminder_notifies_only_recipient_and_preserves_read_state(self):
        self.message.leido = True
        self.message.save(update_fields=['leido'])
        with patch('calificaciones.api_mensajes._reminders.push_unread_update_for_notification') as push:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.post()
            self.assertEqual(response.status_code, 201, response.data)
            push.assert_called_once()
        notif = Notificacion.objects.get(meta__recordatorio=True)
        self.assertEqual(notif.destinatario_id, self.recipient.id)
        self.assertEqual(notif.url, f'/mensajes/hilo/{self.message.id}')
        self.message.refresh_from_db()
        self.assertTrue(self.message.leido)
        self.assertEqual(Mensaje.objects.count(),1)

    def test_cooldown_blocks_duplicates_and_allows_after_24_hours(self):
        self.assertEqual(self.post().status_code, 201)
        self.assertEqual(self.post().status_code, 429)
        self.assertEqual(Notificacion.objects.filter(meta__recordatorio=True).count(),1)
        Mensaje.objects.filter(pk=self.message.pk).update(ultimo_recordatorio_en=timezone.now()-timedelta(hours=24,seconds=1))
        self.assertEqual(self.post().status_code, 201)

    def test_only_original_sender_can_remind_or_resolve(self):
        for user in [self.recipient,self.stranger]:
            self.client.force_authenticate(user)
            self.assertEqual(self.post().status_code,404)
            self.assertEqual(self.post('resolver').status_code,404)
        self.assertFalse(Notificacion.objects.filter(meta__recordatorio=True).exists())

    def test_response_blocks_reminders(self):
        Mensaje.objects.create(school=self.school, school_course=self.course, alumno=self.student, remitente=self.recipient, destinatario=self.sender, asunto='Re: Citación', contenido='Confirmo')
        self.assertEqual(self.post().status_code,409)
        self.assertTrue(with_reply_status(Mensaje.objects.all()).get(pk=self.message.pk).recordatorio_respondido)

    def test_other_student_response_does_not_close_message(self):
        other=Alumno.objects.create(school=self.school,school_course=self.course,curso='1A',nombre='Otro',id_alumno='REM2')
        Mensaje.objects.create(school=self.school,school_course=self.course,alumno=other,remitente=self.recipient,destinatario=self.sender,asunto='Otro',contenido='Otro hijo')
        self.assertEqual(self.post().status_code,201)

    def test_resolved_message_stops_reminders(self):
        self.assertEqual(self.post('resolver').status_code,200)
        self.assertEqual(self.post().status_code,409)
        self.assertFalse(Notificacion.objects.filter(meta__recordatorio=True).exists())

    def test_other_school_is_denied(self):
        other=School.objects.create(name='Other',slug='reminder-other')
        response=self.client.post(self.url,{},format='json',HTTP_X_SCHOOL=other.slug)
        self.assertEqual(response.status_code,403)
