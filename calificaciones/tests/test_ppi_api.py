from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from calificaciones.models import Alumno, School, SchoolCourse
from calificaciones.models_preceptores import PreceptorCurso, ProfesorCurso, SchoolAdmin, SchoolMembership


@override_settings(SECURE_SSL_REDIRECT=False)
class StudentPpiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.school = School.objects.create(name="PPI school", slug="ppi-school")
        self.other_school = School.objects.create(name="Other PPI school", slug="other-ppi-school")
        self.course = SchoolCourse.objects.create(school=self.school, name="1A", code="1A")
        self.other_course = SchoolCourse.objects.create(school=self.school, name="1B", code="1B")
        self.alumno = Alumno.objects.create(school=self.school, school_course=self.course, curso="1A", nombre="Ana", id_alumno="PPI01")
        self.url = f'/api/alumnos/{self.alumno.id}/'

    def user(self, role):
        user = get_user_model().objects.create_user(username=role)
        user.groups.add(Group.objects.get_or_create(name=role)[0])
        SchoolMembership.objects.create(user=user, school=self.school)
        self.client.force_authenticate(user)
        return user

    def patch(self, data):
        return self.client.patch(self.url, data, format='json', HTTP_X_SCHOOL=self.school.slug)

    def test_eoe_can_mark_unmark_and_persist_without_changing_level(self):
        user = self.user('EOE')
        PreceptorCurso.objects.create(preceptor=user, school=self.school, school_course=self.course, curso='1A')
        self.assertFalse(self.alumno.es_ppi)
        for value in [True, False]:
            response = self.patch({'es_ppi': value})
            self.assertEqual(response.status_code, 200, response.json())
            self.alumno.refresh_from_db()
            self.assertEqual(self.alumno.es_ppi, value)
            self.assertEqual(self.alumno.nivel, 'secundaria')
            response = self.client.get(self.url, HTTP_X_SCHOOL=self.school.slug)
            self.assertEqual(response.json()['es_ppi'], value)
            self.assertTrue(response.json()['can_edit_ppi'])

    def test_unassigned_course_and_other_school_are_denied(self):
        user = self.user('EOE')
        PreceptorCurso.objects.create(preceptor=user, school=self.school, school_course=self.other_course, curso='1B')
        self.assertEqual(self.patch({'es_ppi': True}).status_code, 403)
        response = self.client.patch(self.url, {'es_ppi': True}, format='json', HTTP_X_SCHOOL=self.other_school.slug)
        self.assertIn(response.status_code, [403, 404])
        self.alumno.refresh_from_db()
        self.assertFalse(self.alumno.es_ppi)

    def test_directivo_validates_boolean_and_only_updates_ppi(self):
        self.user('Directivos')
        for payload in [{'es_ppi': 'false'}, {'es_ppi': None}, {}, {'es_ppi': True, 'nombre': 'Changed'}]:
            self.assertEqual(self.patch(payload).status_code, 400)
        self.assertEqual(self.patch({'es_ppi': True}).status_code, 200)
        self.alumno.refresh_from_db()
        self.assertEqual(self.alumno.nombre, 'Ana')

    def test_parent_cannot_read_or_modify_internal_flag(self):
        user = self.user('Padres')
        self.alumno.padre = user
        self.alumno.es_ppi = True
        self.alumno.save()
        response = self.client.get(self.url, HTTP_X_SCHOOL=self.school.slug)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('es_ppi', response.json())
        self.assertEqual(self.patch({'es_ppi': False}).status_code, 403)

    def test_assigned_teacher_can_read_but_cannot_modify(self):
        user = self.user('Profesores')
        ProfesorCurso.objects.create(profesor=user, school=self.school, school_course=self.course, curso='1A')
        response = self.client.get(self.url, HTTP_X_SCHOOL=self.school.slug)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['can_edit_ppi'])
        self.assertEqual(self.patch({'es_ppi': True}).status_code, 403)

    def test_school_admin_can_manage_own_school(self):
        user = self.user('Administradores')
        SchoolAdmin.objects.create(admin=user, school=self.school)
        self.assertEqual(self.patch({'es_ppi': True}).status_code, 200)

    def test_course_rosters_include_current_ppi_flag(self):
        user = self.user('EOE')
        PreceptorCurso.objects.create(preceptor=user, school=self.school, school_course=self.course, curso='1A')
        for value in [True, False]:
            self.assertEqual(self.patch({'es_ppi': value}).status_code, 200)
            for url in [f'/api/alumnos/?school_course_id={self.course.id}', f'/api/alumnos/curso/{self.course.id}/']:
                response = self.client.get(url, HTTP_X_SCHOOL=self.school.slug)
                self.assertEqual(response.status_code, 200, response.json())
                row = next(row for row in response.json()['alumnos'] if row['id'] == self.alumno.id)
                self.assertEqual(row['es_ppi'], value)

    def test_parent_cannot_access_course_ppi_roster(self):
        user = self.user('Padres')
        self.alumno.padre = user
        self.alumno.save()
        response = self.client.get(f'/api/alumnos/?school_course_id={self.course.id}', HTTP_X_SCHOOL=self.school.slug)
        self.assertEqual(response.status_code, 403)
