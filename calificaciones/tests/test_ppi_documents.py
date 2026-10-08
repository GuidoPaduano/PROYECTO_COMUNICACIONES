from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from calificaciones.models import Alumno, PpiDocument, School, SchoolCourse
from calificaciones.models_preceptores import PreceptorCurso, ProfesorCurso, SchoolMembership

PDF = b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF'


@override_settings(SECURE_SSL_REDIRECT=False)
class PpiDocumentsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.school = School.objects.create(name='PPI docs', slug='ppi-docs')
        self.other_school = School.objects.create(name='Other', slug='ppi-other')
        self.course = SchoolCourse.objects.create(school=self.school, code='1A', name='1A')
        self.other_course = SchoolCourse.objects.create(school=self.school, code='1B', name='1B')
        self.alumno = Alumno.objects.create(school=self.school, school_course=self.course, curso='1A', id_alumno='PPI1', nombre='Ana', es_ppi=True)
        self.client = APIClient()
        self.url = f'/api/alumnos/{self.alumno.id}/ppi-documentos'

    def login(self, role, course=None):
        user = get_user_model().objects.create_user(username=role)
        user.groups.add(Group.objects.get_or_create(name=role)[0])
        SchoolMembership.objects.create(school=self.school, user=user)
        if course:
            if role == 'Profesores':
                ProfesorCurso.objects.create(profesor=user, school=self.school, school_course=course, curso=course.code)
            else:
                PreceptorCurso.objects.create(preceptor=user, school=self.school, school_course=course, curso=course.code)
        self.client.force_authenticate(user)
        return user

    def upload(self, content=PDF, filename='informe.pdf'):
        return self.client.post(self.url, {'titulo':'Informe', 'archivo': SimpleUploadedFile(filename, content, content_type='application/pdf')}, format='multipart', HTTP_X_SCHOOL=self.school.slug)

    def test_integracion_upload_list_download(self):
        self.login('Integracion', self.course)
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.data)
        doc_id = response.data['document']['id']
        listing = self.client.get(self.url, HTTP_X_SCHOOL=self.school.slug)
        self.assertTrue(listing.data['can_upload'])
        self.assertEqual(listing.data['documents'][0]['id'], doc_id)
        self.assertNotIn('contenido', listing.data['documents'][0])
        response = self.client.get(f'{self.url}/{doc_id}/archivo', HTTP_X_SCHOOL=self.school.slug)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), PDF)
        self.assertEqual(response['Cache-Control'], 'private, no-store')

    def test_assigned_teacher_can_read_but_not_upload(self):
        self.login('Profesores', self.course)
        doc = PpiDocument.objects.create(alumno=self.alumno, titulo='Informe', nombre_archivo='informe.pdf', contenido=PDF, tamano=len(PDF))
        self.assertEqual(self.upload().status_code, 403)
        self.assertFalse(self.client.get(self.url, HTTP_X_SCHOOL=self.school.slug).data['can_upload'])
        self.assertEqual(self.client.get(f'{self.url}/{doc.id}/archivo', HTTP_X_SCHOOL=self.school.slug).status_code, 200)

    def test_unassigned_integration_is_denied(self):
        self.login('Integracion', self.other_course)
        self.assertEqual(self.upload().status_code, 403)
        self.assertEqual(self.client.get(self.url, HTTP_X_SCHOOL=self.school.slug).status_code, 403)

    def test_parent_and_other_school_cannot_download(self):
        doc = PpiDocument.objects.create(alumno=self.alumno, titulo='Informe', nombre_archivo='informe.pdf', contenido=PDF, tamano=len(PDF))
        self.login('Padres')
        self.assertEqual(self.client.get(f'{self.url}/{doc.id}/archivo', HTTP_X_SCHOOL=self.school.slug).status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f'{self.url}/{doc.id}/archivo').status_code, 401)

    def test_other_student_document_is_not_accessible(self):
        self.login('Integracion', self.course)
        other = Alumno.objects.create(school=self.school, school_course=self.other_course, curso='1B', id_alumno='PPI2', nombre='Otra', es_ppi=True)
        doc = PpiDocument.objects.create(alumno=other, titulo='Otro', nombre_archivo='otro.pdf', contenido=PDF, tamano=len(PDF))
        self.assertEqual(self.client.get(f'{self.url}/{doc.id}/archivo', HTTP_X_SCHOOL=self.school.slug).status_code, 404)
        self.assertIn(self.client.get(self.url, HTTP_X_SCHOOL=self.other_school.slug).status_code, [403,404])

    def test_invalid_pdf_and_non_ppi_rejected_without_losing_documents(self):
        self.login('Integracion', self.course)
        self.assertEqual(self.upload(b'not a pdf').status_code, 400)
        self.assertEqual(self.upload(PDF, 'file.exe').status_code, 400)
        self.assertEqual(self.upload().status_code, 201)
        self.alumno.es_ppi = False
        self.alumno.save(update_fields=['es_ppi'])
        self.assertEqual(self.upload().status_code, 403)
        self.assertEqual(self.client.get(self.url, HTTP_X_SCHOOL=self.school.slug).status_code, 403)
        self.assertEqual(PpiDocument.objects.filter(alumno=self.alumno).count(), 1)

    def test_admin_can_create_integration_user_with_courses(self):
        admin = get_user_model().objects.create_user(username='admin', is_superuser=True)
        self.client.force_authenticate(admin)
        response = self.client.post('/api/admin/users/create/', {'username':'integracion_nueva','first_name':'Ana','last_name':'Docente','email':'integ@example.com','password':'Integracion-9955!','password_confirm':'Integracion-9955!','role':'Integracion','school_course_ids':[self.course.id]}, format='json', HTTP_X_SCHOOL=self.school.slug)
        self.assertEqual(response.status_code, 201, response.data)
        user = get_user_model().objects.get(username='integracion_nueva')
        self.assertEqual(list(user.groups.values_list('name',flat=True)), ['Integracion'])
        self.assertTrue(PreceptorCurso.objects.filter(preceptor=user, school_course=self.course).exists())
