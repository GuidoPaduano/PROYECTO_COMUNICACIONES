from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from calificaciones.models import School, SchoolCourse
from calificaciones.models_preceptores import PreceptorCurso
from calificaciones.user_groups import get_user_group_names
from calificaciones.views._acceso import _preceptor_can_access_curso


@override_settings(SECURE_SSL_REDIRECT=False)
class EOERoleTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="EOE school", slug="eoe-school")
        self.course = SchoolCourse.objects.create(school=self.school, code="1A", name="1A")
        self.other = SchoolCourse.objects.create(school=self.school, code="1B", name="1B")
        self.admin = get_user_model().objects.create_user(username="eoe_admin", is_superuser=True)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def create_eoe(self):
        response = self.client.post('/api/admin/users/create/', {
            'username': 'eoe_user', 'first_name': 'Equipo', 'last_name': 'Orientacion',
            'email': 'eoe@example.com', 'password': 'EOE-secure-9842!',
            'password_confirm': 'EOE-secure-9842!', 'role': 'EOE',
            'school_course_ids': [self.course.id],
        }, format='json', HTTP_X_SCHOOL=self.school.slug)
        self.assertEqual(response.status_code, 201, response.json())
        return get_user_model().objects.get(username='eoe_user')

    def test_creation_identity_permissions_and_scope(self):
        user = self.create_eoe()
        self.assertEqual(list(user.groups.values_list('name', flat=True)), ['EOE'])
        self.assertIn('Preceptores', get_user_group_names(user))
        self.assertTrue(_preceptor_can_access_curso(user, school=self.school, school_course=self.course))
        self.assertFalse(_preceptor_can_access_curso(user, school=self.school, school_course=self.other))
        self.client.force_authenticate(user)
        for path in ['/api/auth/whoami/', '/api/perfil_api/']:
            response = self.client.get(path, HTTP_X_SCHOOL=self.school.slug)
            self.assertEqual(response.status_code, 200, response.json())
        response = self.client.get('/api/auth/whoami/', HTTP_X_SCHOOL=self.school.slug)
        self.assertEqual(response.json()['rol'], 'EOE')
        response = self.client.get('/api/admin/staff/', HTTP_X_SCHOOL=self.school.slug)
        self.assertEqual(response.status_code, 403)

    def test_assignment_updates_preserve_other_role(self):
        eoe = self.create_eoe()
        preceptor = get_user_model().objects.create_user(username='prec')
        preceptor.groups.add(Group.objects.get_or_create(name='Preceptores')[0])
        PreceptorCurso.objects.create(preceptor=preceptor, school=self.school, school_course=self.course, curso='1A')
        for role, expected in [('EOE', preceptor), ('Preceptores', eoe)]:
            if role == 'Preceptores':
                PreceptorCurso.objects.get_or_create(preceptor=eoe, school=self.school, school_course=self.course, defaults={'curso': '1A'})
            response = self.client.patch(f'/api/admin/staff/course/{self.course.id}/', {'staff_role': role, 'user_ids': []}, format='json', HTTP_X_SCHOOL=self.school.slug)
            self.assertEqual(response.status_code, 200, response.json())
            self.assertTrue(PreceptorCurso.objects.filter(preceptor=expected, school_course=self.course).exists())

    def test_preview_and_staff_identity(self):
        user = self.create_eoe()
        response = self.client.get('/api/admin/staff/', HTTP_X_SCHOOL=self.school.slug)
        row = next(row for row in response.json()['users'] if row['id'] == user.id)
        self.assertEqual(row['staff_role'], 'EOE')
        response = self.client.get('/api/auth/whoami/', HTTP_X_SCHOOL=self.school.slug, HTTP_X_PREVIEW_ROLE='EOE')
        self.assertEqual(response.status_code, 200)
        self.assertIn('EOE', response.json()['groups'])
        self.assertIn('Preceptores', response.json()['groups'])

    def test_attendance_requires_assigned_course(self):
        from datetime import date
        from calificaciones.models import Alumno, Asistencia
        user = self.create_eoe()
        self.client.force_authenticate(user)
        for course, expected_status in [(self.course, 200), (self.other, 403)]:
            alumno = Alumno.objects.create(nombre='Ana', apellido='Prueba', id_alumno=f'EOE{course.id}', school=self.school, school_course=course, curso=course.code)
            response = self.client.post('/api/asistencias/registrar/', {
                'school_course_id': course.id, 'fecha': str(date.today()),
                'tipo_asistencia': 'clases', 'asistencias': {str(alumno.id): 'ausente'},
            }, format='json', HTTP_X_SCHOOL=self.school.slug)
            self.assertEqual(response.status_code, expected_status, response.json())
            self.assertEqual(Asistencia.objects.filter(alumno=alumno).exists(), expected_status == 200)
