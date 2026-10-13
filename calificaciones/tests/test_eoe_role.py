from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from calificaciones.models import Alumno, School, SchoolCourse
from calificaciones.models_preceptores import PreceptorCurso, SchoolMembership


@override_settings(SECURE_SSL_REDIRECT=False)
class EOERoleTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name='EOE school', slug='eoe-school')
        self.other_school = School.objects.create(name='Other', slug='other-eoe')
        self.course = SchoolCourse.objects.create(school=self.school, code='1A', name='1A')
        self.other = SchoolCourse.objects.create(school=self.school, code='1B', name='1B')
        self.admin = get_user_model().objects.create_user(username='eoe_admin', is_superuser=True)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def create_eoe(self):
        response = self.client.post('/api/admin/users/create/', {
            'username': 'eoe_user', 'first_name': 'Equipo', 'last_name': 'Orientacion',
            'email': 'eoe@example.com', 'password': 'EOE-secure-9842!',
            'password_confirm': 'EOE-secure-9842!', 'role': 'EOE', 'school_course_ids': [],
        }, format='json', HTTP_X_SCHOOL=self.school.slug)
        self.assertEqual(response.status_code, 201, response.data)
        return get_user_model().objects.get(username='eoe_user')

    def test_creation_membership_and_staff_identity_without_courses(self):
        user = self.create_eoe()
        self.assertEqual(list(user.groups.values_list('name', flat=True)), ['EOE'])
        self.assertTrue(SchoolMembership.objects.filter(user=user, school=self.school, is_active=True).exists())
        self.assertFalse(PreceptorCurso.objects.filter(preceptor=user).exists())
        response = self.client.get('/api/admin/staff/', HTTP_X_SCHOOL=self.school.slug)
        row = next(row for row in response.data['users'] if row['id'] == user.id)
        self.assertEqual(row['staff_role'], 'EOE')
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get('/api/auth/whoami/', HTTP_X_SCHOOL=self.school.slug).json()['rol'], 'EOE')

    def test_all_ppi_students_are_accessible_without_course_assignments(self):
        user = self.create_eoe()
        expected = []
        for course in [self.course, self.other]:
            a = Alumno.objects.create(school=self.school, school_course=course, curso=course.code, id_alumno=f'PPI{course.id}', nombre='Ana', es_ppi=True)
            expected.append(a.id)
        non_ppi = Alumno.objects.create(school=self.school, school_course=self.course, curso='1A', id_alumno='REG', nombre='Otro')
        self.client.force_authenticate(user)
        response = self.client.get('/api/eoe/alumnos', HTTP_X_SCHOOL=self.school.slug)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual({a['id'] for a in response.data['alumnos']}, set(expected))
        for pk in expected:
            self.assertEqual(self.client.get(f'/api/alumnos/{pk}/', HTTP_X_SCHOOL=self.school.slug).status_code, 200)
            docs = self.client.get(f'/api/alumnos/{pk}/ppi-documentos', HTTP_X_SCHOOL=self.school.slug)
            self.assertEqual(docs.status_code, 200, docs.data)
            self.assertTrue(docs.data['can_upload'])
        self.assertEqual(self.client.get(f'/api/alumnos/{non_ppi.id}/', HTTP_X_SCHOOL=self.school.slug).status_code, 403)
        self.assertEqual(self.client.get('/api/eoe/alumnos', HTTP_X_SCHOOL=self.other_school.slug).status_code, 403)
        SchoolMembership.objects.filter(user=user).update(is_active=False)
        self.assertEqual(self.client.get('/api/eoe/alumnos', HTTP_X_SCHOOL=self.school.slug).status_code, 403)

    def test_course_assignment_rejected(self):
        user = self.create_eoe()
        response = self.client.patch(f'/api/admin/staff/course/{self.course.id}/', {'staff_role':'EOE', 'user_ids':[user.id]}, format='json', HTTP_X_SCHOOL=self.school.slug)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(PreceptorCurso.objects.filter(preceptor=user).exists())

    def test_teacher_cannot_open_eoe_roster(self):
        from django.contrib.auth.models import Group
        user = get_user_model().objects.create_user(username='teacher')
        user.groups.add(Group.objects.get_or_create(name='Profesores')[0])
        SchoolMembership.objects.create(school=self.school,user=user)
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get('/api/eoe/alumnos', HTTP_X_SCHOOL=self.school.slug).status_code, 403)
