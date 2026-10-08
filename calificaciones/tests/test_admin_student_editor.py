from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from calificaciones.models import Alumno, Asistencia, School, SchoolCourse
from calificaciones.models_preceptores import SchoolAdmin
from django.utils import timezone


@override_settings(SECURE_SSL_REDIRECT=False)
class AdminStudentEditorTests(TestCase):
    def setUp(self):
        cache.clear()
        self.school = School.objects.create(name='Norte', slug='editor-norte')
        self.other = School.objects.create(name='Sur', slug='editor-sur')
        self.course = SchoolCourse.objects.create(school=self.school, code='1A', name='1A', nivel='secundaria')
        self.primary = SchoolCourse.objects.create(school=self.school, code='1P', name='Primero', nivel='primaria')
        self.foreign = SchoolCourse.objects.create(school=self.other, code='1A', name='1A')
        self.admin = get_user_model().objects.create_user(username='editor_admin')
        self.admin.groups.add(Group.objects.get_or_create(name='Administradores')[0])
        SchoolAdmin.objects.create(school=self.school, admin=self.admin)
        self.student_user = get_user_model().objects.create_user(username='student_login')
        self.parent = get_user_model().objects.create_user(username='parent')
        self.student = Alumno.objects.create(school=self.school, school_course=self.course, curso='1A', nombre='Ana', apellido='Perez', id_alumno='A001', usuario=self.student_user, padre=self.parent)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.url = f'/api/admin/students/{self.student.id}/'

    def patch(self, data):
        return self.client.patch(self.url, data, format='json', HTTP_X_SCHOOL=self.school.slug)

    def test_search_by_name_or_record_with_school_scope(self):
        Alumno.objects.create(school=self.other, school_course=self.foreign, curso='1A', nombre='Ana', apellido='Perez', id_alumno='A001')
        for query in ['Ana Perez', 'Perez Ana', 'A001']:
            response = self.client.get('/api/admin/students/', {'q': query}, HTTP_X_SCHOOL=self.school.slug)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['count'], 1)
            self.assertEqual(response.json()['students'][0]['id'], self.student.id)
            self.assertNotIn(self.foreign.id, [c['id'] for c in response.json()['courses']])

    def test_edit_preserves_history_and_links_and_sets_course_level(self):
        attendance = Asistencia.objects.create(alumno=self.student, school=self.school, fecha=timezone.localdate(), tipo_asistencia='clases', presente=True)
        response = self.patch({'nombre': 'Ana Maria', 'apellido': 'Gomez', 'id_alumno': 'A002', 'es_ppi': True, 'school_course_id': self.primary.id})
        self.assertEqual(response.status_code, 200, response.json())
        self.student.refresh_from_db()
        self.assertEqual((self.student.nombre, self.student.apellido, self.student.id_alumno), ('Ana Maria', 'Gomez', 'A002'))
        self.assertEqual((self.student.school_course_id, self.student.curso, self.student.nivel), (self.primary.id, '1P', 'primaria'))
        self.assertTrue(self.student.es_ppi)
        self.assertEqual((self.student.padre_id, self.student.usuario_id), (self.parent.id, self.student_user.id))
        attendance.refresh_from_db()
        self.assertEqual(attendance.alumno_id, self.student.id)
        self.student_user.refresh_from_db()
        self.assertEqual(self.student_user.username, 'student_login')

    def test_duplicate_record_rejects_entire_change(self):
        Alumno.objects.create(school=self.school, school_course=self.course, curso='1A', nombre='Otra', apellido='Persona', id_alumno='DUP')
        response = self.patch({'id_alumno': 'dup', 'es_ppi': True})
        self.assertEqual(response.status_code, 400)
        self.student.refresh_from_db()
        self.assertEqual(self.student.id_alumno, 'A001')
        self.assertFalse(self.student.es_ppi)

    def test_invalid_fields_and_foreign_course_are_rejected(self):
        for data in [{'nivel': 'primaria'}, {'padre_id': self.admin.id}, {'es_ppi': 'false'}, {'nombre': ''}, {'apellido': 'Perez2'}, {'school_course_id': self.foreign.id}, {'school_course_id': True}]:
            self.assertEqual(self.patch(data).status_code, 400, data)

    def test_cannot_move_to_inactive_course_but_can_keep_current(self):
        self.primary.is_active = False
        self.primary.save()
        self.assertEqual(self.patch({'school_course_id': self.primary.id}).status_code, 400)
        self.course.is_active = False
        self.course.save()
        self.assertEqual(self.patch({'school_course_id': self.course.id, 'es_ppi': True}).status_code, 200)

    def test_other_school_and_non_admin_are_denied(self):
        response = self.client.patch(self.url, {'es_ppi': True}, format='json', HTTP_X_SCHOOL=self.other.slug)
        self.assertEqual(response.status_code, 403)
        foreign_student = Alumno.objects.create(school=self.other, school_course=self.foreign, curso='1A', nombre='Otra', id_alumno='OTHER')
        response = self.client.patch(f'/api/admin/students/{foreign_student.id}/', {'es_ppi': True}, format='json', HTTP_X_SCHOOL=self.school.slug)
        self.assertEqual(response.status_code, 404)
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.patch({'es_ppi': True}).status_code, 403)
        self.assertEqual(self.client.get('/api/admin/students/', HTTP_X_SCHOOL=self.school.slug).status_code, 403)

    def test_pagination(self):
        for i in range(51):
            Alumno.objects.create(school=self.school, school_course=self.course, curso='1A', nombre='Alumno', id_alumno=f'P{i}')
        first = self.client.get('/api/admin/students/', HTTP_X_SCHOOL=self.school.slug).json()
        second = self.client.get('/api/admin/students/?page=2', HTTP_X_SCHOOL=self.school.slug).json()
        self.assertEqual(len(first['students']), 50)
        self.assertTrue(first['has_next'])
        self.assertEqual(len(second['students']), 2)
        self.assertFalse(second['has_next'])
        self.assertFalse({s['id'] for s in first['students']} & {s['id'] for s in second['students']})

    def test_detail_includes_account_tutor_and_courses(self):
        response = self.client.get(self.url, HTTP_X_SCHOOL=self.school.slug)
        self.assertEqual(response.status_code, 200)
        student = response.json()['student']
        self.assertEqual(student['linked_user']['username'], 'student_login')
        self.assertEqual(student['parent_user']['username'], 'parent')
        self.assertEqual(student['school_course_id'], self.course.id)
        self.assertFalse(student['es_ppi'])
        denied = self.client.get(self.url, HTTP_X_SCHOOL=self.other.slug)
        self.assertEqual(denied.status_code, 403)
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.client.get(self.url, HTTP_X_SCHOOL=self.school.slug).status_code, 403)

    def test_slashless_routes_support_proxy_reads_and_updates(self):
        for url in ['/api/admin/students', self.url.rstrip('/')]:
            response = self.client.get(url, HTTP_X_SCHOOL=self.school.slug)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('Location', response.headers)
        response = self.client.patch(self.url.rstrip('/'), {'es_ppi': True}, format='json', HTTP_X_SCHOOL=self.school.slug)
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertTrue(self.student.es_ppi)
