import hashlib
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from calificaciones.models import Alumno, Notificacion, PpiDocument, PpiDocumentReceipt, School, SchoolCourse
from calificaciones.models_preceptores import PreceptorCurso, ProfesorCurso, ProfesorCursoMateria, SchoolMembership

PDF = b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF'


@override_settings(SECURE_SSL_REDIRECT=False)
class PpiReadReceiptsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.school = School.objects.create(name='School', slug='ppi-sign-school')
        self.other_school = School.objects.create(name='Other', slug='ppi-sign-other')
        self.course = SchoolCourse.objects.create(school=self.school, code='1A', name='1A')
        self.other_course = SchoolCourse.objects.create(school=self.school, code='1B', name='1B')
        self.alumno = Alumno.objects.create(school=self.school, school_course=self.course, curso='1A', id_alumno='PPI1', nombre='Ana', es_ppi=True)
        self.client = APIClient()
        self.url = f'/api/alumnos/{self.alumno.id}/ppi-documentos'
        self.eoe = self.user('eoe', 'EOE')
        PreceptorCurso.objects.create(preceptor=self.eoe, school=self.school, school_course=self.course, curso='1A')
        self.teacher = self.user('teacher', 'Profesores')
        self.second = self.user('second', 'Profesores')
        self.outsider = self.user('outsider', 'Profesores')
        for teacher in [self.teacher, self.second]:
            ProfesorCurso.objects.create(profesor=teacher, school=self.school, school_course=self.course, curso='1A')
        ProfesorCurso.objects.create(profesor=self.outsider, school=self.school, school_course=self.other_course, curso='1B')
        self.client.force_authenticate(self.eoe)

    def user(self, username, role):
        user = get_user_model().objects.create_user(username=username)
        user.groups.add(Group.objects.get_or_create(name=role)[0])
        SchoolMembership.objects.create(school=self.school, user=user)
        return user

    def get(self, path):
        return self.client.get(path, HTTP_X_SCHOOL=self.school.slug)

    def post(self, path, data=None):
        return self.client.post(path, data or {}, format='json', HTTP_X_SCHOOL=self.school.slug)

    def upload(self, **extra):
        data = {'titulo': 'Recomendaciones', 'archivo': SimpleUploadedFile('guia.pdf', PDF, content_type='application/pdf'), 'requiere_firma': 'true', 'docentes': json.dumps([self.teacher.id])}
        data.update(extra)
        return self.client.post(self.url, data, format='multipart', HTTP_X_SCHOOL=self.school.slug)

    def create_doc(self):
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.data)
        return PpiDocument.objects.get(pk=response.data['document']['id'])

    def sign(self, doc):
        return self.post(f'{self.url}/{doc.id}/firmar', {'confirmo_lectura': True})

    def test_eoe_publishes_to_selected_teachers_and_records_pdf_version(self):
        doc = self.create_doc()
        self.assertEqual(doc.sha256, hashlib.sha256(PDF).hexdigest())
        self.assertEqual(doc.version, 1)
        self.assertEqual(list(doc.receipts.values_list('docente_id', flat=True)), [self.teacher.id])
        notification = Notificacion.objects.get(destinatario=self.teacher)
        self.assertIn(f'ppi_document={doc.id}', notification.url)
        self.assertFalse(Notificacion.objects.filter(destinatario=self.second).exists())
        listing = self.get(self.url)
        self.assertTrue(listing.data['can_upload'])
        self.assertEqual({r['id'] for r in listing.data['docentes']}, {self.teacher.id, self.second.id})
        self.assertEqual(listing.data['documents'][0]['destinatarios'][0]['nombre'], 'teacher')

    def test_invalid_recipients_do_not_create_documents_or_notifications(self):
        for recipients in [[], [self.outsider.id], [self.teacher.id, self.outsider.id], [999999], ['1'], {'a': 1}]:
            self.assertEqual(self.upload(docentes=json.dumps(recipients)).status_code, 400)
        self.assertFalse(PpiDocument.objects.exists())
        self.assertFalse(Notificacion.objects.exists())

    def test_subject_assignment_is_an_eligible_teacher(self):
        subject_teacher = self.user('subject', 'Profesores')
        ProfesorCursoMateria.objects.create(profesor=subject_teacher, school=self.school, school_course=self.course, materia='Matemática')
        response = self.upload(docentes=json.dumps([subject_teacher.id]))
        self.assertEqual(response.status_code, 201, response.data)

    def test_self_signature_is_not_offered_or_accepted(self):
        self.eoe.groups.add(Group.objects.get_or_create(name='Profesores')[0])
        ProfesorCurso.objects.create(profesor=self.eoe, school=self.school, school_course=self.course, curso='1A')
        self.assertEqual(self.upload(docentes=json.dumps([self.eoe.id])).status_code, 400)

    def test_only_explicit_confirmation_after_consultation_signs(self):
        doc = self.create_doc()
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.sign(doc).status_code, 400)
        response = self.get(f'{self.url}/{doc.id}/archivo')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), PDF)
        receipt = doc.receipts.get()
        self.assertIsNotNone(receipt.consultado_en)
        self.assertIsNone(receipt.firmado_en)
        self.assertEqual(self.post(f'{self.url}/{doc.id}/firmar').status_code, 400)
        self.assertEqual(self.post(f'{self.url}/{doc.id}/firmar', {'confirmo_lectura': 'true'}).status_code, 400)
        self.assertEqual(self.sign(doc).status_code, 200)
        receipt.refresh_from_db()
        self.assertEqual(receipt.declaracion, 'Confirmo que leí las recomendaciones de este documento.')
        signed_at = receipt.firmado_en
        self.assertEqual(self.sign(doc).status_code, 200)
        receipt.refresh_from_db()
        self.assertEqual(receipt.firmado_en, signed_at)
        self.assertEqual(doc.receipts.count(), 1)

    def test_recipient_inbox_and_other_teacher_isolation(self):
        doc = self.create_doc()
        self.client.force_authenticate(self.teacher)
        inbox = self.get('/api/ppi-documentos/recibidos')
        self.assertEqual(inbox.status_code, 200)
        self.assertEqual(inbox.data['documents'][0]['id'], doc.id)
        self.assertTrue(inbox.data['documents'][0]['puede_firmar'])
        self.assertNotIn('destinatarios', inbox.data['documents'][0])
        self.client.force_authenticate(self.second)
        self.assertEqual(self.get(self.url).data['documents'], [])
        self.assertEqual(self.get('/api/ppi-documentos/recibidos').data['documents'], [])
        self.assertEqual(self.get(f'{self.url}/{doc.id}/archivo').status_code, 404)
        self.assertEqual(self.sign(doc).status_code, 403)

    def test_removed_course_assignment_revokes_download_sign_and_inbox(self):
        doc = self.create_doc()
        ProfesorCurso.objects.filter(profesor=self.teacher).delete()
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.get('/api/ppi-documentos/recibidos').data['documents'], [])
        self.assertEqual(self.get(f'{self.url}/{doc.id}/archivo').status_code, 403)
        self.assertEqual(self.sign(doc).status_code, 403)

    def test_school_and_student_boundaries_and_authentication(self):
        doc = self.create_doc()
        self.assertEqual(self.client.get(self.url, HTTP_X_SCHOOL=self.other_school.slug).status_code, 403)
        other = Alumno.objects.create(school=self.school, school_course=self.course, curso='1A', id_alumno='PPI2', nombre='Otra', es_ppi=True)
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.get(f'/api/alumnos/{other.id}/ppi-documentos/{doc.id}/archivo').status_code, 404)
        self.assertEqual(self.post(f'/api/alumnos/{other.id}/ppi-documentos/{doc.id}/firmar', {'confirmo_lectura': True}).status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.get('/api/ppi-documentos/recibidos').status_code, 401)
        self.assertEqual(self.sign(doc).status_code, 401)

    def test_new_version_preserves_signatures_and_requires_a_fresh_one(self):
        doc = self.create_doc()
        self.client.force_authenticate(self.teacher)
        self.get(f'{self.url}/{doc.id}/archivo')
        self.sign(doc)
        old_receipt = doc.receipts.get()
        self.client.force_authenticate(self.eoe)
        result = self.upload(version_anterior_id=str(doc.id))
        self.assertEqual(result.status_code, 201, result.data)
        new = PpiDocument.objects.get(pk=result.data['document']['id'])
        self.assertEqual(new.version, 2)
        self.assertEqual(new.version_anterior, doc)
        self.assertEqual(doc.receipts.get().firmado_en, old_receipt.firmado_en)
        self.assertIsNone(new.receipts.get().firmado_en)
        self.assertIsNone(new.receipts.get().consultado_en)
        self.assertEqual(bytes(doc.contenido), PDF)
        self.assertEqual(self.upload(version_anterior_id=str(doc.id)).status_code, 409)
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.sign(new).status_code, 400)
        self.assertTrue(self.get('/api/ppi-documentos/recibidos').data['documents'][0]['puede_firmar'])

    def test_superseded_pending_version_cannot_be_signed_or_reminded(self):
        doc = self.create_doc()
        self.client.force_authenticate(self.teacher)
        self.get(f'{self.url}/{doc.id}/archivo')
        self.client.force_authenticate(self.eoe)
        self.assertEqual(self.upload(version_anterior_id=str(doc.id), requiere_firma='false').status_code, 400)
        self.assertEqual(self.upload(version_anterior_id=str(doc.id)).status_code, 201)
        self.assertEqual(self.post(f'{self.url}/{doc.id}/recordar/{self.teacher.id}').status_code, 409)
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.sign(doc).status_code, 409)

    def test_reminder_immediate_cooldown_and_signed_stop(self):
        doc = self.create_doc()
        endpoint = f'{self.url}/{doc.id}/recordar/{self.teacher.id}'
        self.assertEqual(self.post(endpoint).status_code, 201)
        self.assertEqual(Notificacion.objects.filter(destinatario=self.teacher).count(), 2)
        self.assertEqual(self.post(endpoint).status_code, 429)
        doc.receipts.update(ultimo_recordatorio_en=timezone.now() - timedelta(hours=25))
        self.assertEqual(self.post(endpoint).status_code, 201)
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.post(endpoint).status_code, 403)
        self.get(f'{self.url}/{doc.id}/archivo')
        self.sign(doc)
        self.client.force_authenticate(self.eoe)
        self.assertEqual(self.post(endpoint).status_code, 409)

    def test_eoe_outside_assigned_course_cannot_publish_or_remind(self):
        doc = self.create_doc()
        unassigned = self.user('unassigned', 'EOE')
        PreceptorCurso.objects.create(preceptor=unassigned, school=self.school, school_course=self.other_course, curso='1B')
        self.client.force_authenticate(unassigned)
        self.assertEqual(self.upload().status_code, 403)
        self.assertEqual(self.post(f'{self.url}/{doc.id}/recordar/{self.teacher.id}').status_code, 403)
