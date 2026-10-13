from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from calificaciones.models import Alumno, IntegrationStudentAssignment, PpiDocument, School, SchoolCourse
from calificaciones.models_preceptores import PreceptorCurso, SchoolMembership


@override_settings(SECURE_SSL_REDIRECT=False)
class IntegrationAssignmentTests(TestCase):
    def setUp(self):
        cache.clear()
        self.school = School.objects.create(name='Integration school', slug='integration-school')
        self.other = School.objects.create(name='Other', slug='other-integration')
        self.course = SchoolCourse.objects.create(school=self.school, code='1A', name='1A')
        self.other_course = SchoolCourse.objects.create(school=self.other, code='1A', name='1A')
        self.student = self.student_at('A', self.school, self.course)
        self.classmate = self.student_at('B', self.school, self.course)
        self.external = self.student_at('C', self.other, self.other_course)
        self.teacher = self.user('integration', 'Integracion', self.school)
        self.second = self.user('second', 'Integracion', self.school)
        self.outsider = self.user('outsider', 'Integracion', self.other)
        self.eoe = self.user('eoe', 'EOE', self.school)
        self.admin = get_user_model().objects.create_user(username='admin', is_superuser=True)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.url = f'/api/admin/integracion/alumnos/{self.student.pk}'

    def student_at(self, name, school, course):
        return Alumno.objects.create(nombre=name, id_alumno=name, school=school, school_course=course, curso=course.code, es_ppi=True)

    def user(self, name, role, school):
        user = get_user_model().objects.create_user(username=name)
        user.groups.add(Group.objects.get_or_create(name=role)[0])
        SchoolMembership.objects.create(user=user, school=school)
        return user

    def get(self, path):
        return self.client.get(path, HTTP_X_SCHOOL=self.school.slug)

    def assign(self, ids, path=None):
        return self.client.patch(path or self.url, {'maestra_ids': ids}, format='json', HTTP_X_SCHOOL=self.school.slug)

    def test_multiple_teachers_one_student_and_idempotent_save(self):
        response = self.assign([self.teacher.pk, self.second.pk, self.teacher.pk])
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(IntegrationStudentAssignment.objects.count(), 2)
        self.assertEqual(self.assign([self.teacher.pk, self.second.pk]).status_code, 200)
        self.assertEqual(IntegrationStudentAssignment.objects.count(), 2)
        overview = self.get('/api/admin/integracion/alumnos')
        self.assertEqual(overview.status_code, 200)
        self.assertEqual({t['id'] for t in overview.data['maestras']}, {self.teacher.pk, self.second.pk})
        self.assertNotIn(self.external.pk, [a['id'] for a in overview.data['alumnos']])

    def test_only_assigned_student_profile_and_documents_are_accessible(self):
        self.assign([self.teacher.pk])
        self.client.force_authenticate(self.teacher)
        roster = self.get('/api/integracion/alumnos')
        self.assertEqual([a['id'] for a in roster.data['alumnos']], [self.student.pk])
        self.assertEqual(self.get(f'/api/alumnos/{self.student.pk}/').status_code, 200)
        self.assertEqual(self.get(f'/api/alumnos/{self.classmate.pk}/').status_code, 403)
        url = f'/api/alumnos/{self.student.pk}/ppi-documentos'
        response = self.client.post(url, {'titulo':'Informe', 'archivo':SimpleUploadedFile('informe.pdf', b'%PDF-1.4\n%%EOF')}, format='multipart', HTTP_X_SCHOOL=self.school.slug)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(self.get(url).data['can_upload'])
        other_doc = PpiDocument.objects.create(alumno=self.classmate, titulo='Otro', nombre_archivo='otro.pdf', contenido=b'%PDF-1.4', tamano=8)
        self.assertEqual(self.get(f'/api/alumnos/{self.classmate.pk}/ppi-documentos/{other_doc.pk}/archivo').status_code, 403)

    def test_unassignment_revokes_access_without_deleting_documents(self):
        self.assign([self.teacher.pk])
        doc = PpiDocument.objects.create(alumno=self.student, titulo='Informe', nombre_archivo='informe.pdf', contenido=b'%PDF-1.4', tamano=8, subido_por=self.teacher)
        self.assertEqual(self.assign([]).status_code, 200)
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.get('/api/integracion/alumnos').data['alumnos'], [])
        self.assertEqual(self.get(f'/api/alumnos/{self.student.pk}/ppi-documentos/{doc.pk}/archivo').status_code, 403)
        self.assertTrue(PpiDocument.objects.filter(pk=doc.pk).exists())

    def test_inactive_or_other_school_or_other_role_teacher_cannot_be_assigned(self):
        SchoolMembership.objects.filter(user=self.second).update(is_active=False)
        for ids in [[self.second.pk], [self.outsider.pk], [self.eoe.pk], [999999]]:
            self.assertEqual(self.assign(ids).status_code, 400)
        self.assertFalse(IntegrationStudentAssignment.objects.exists())

    def test_invalid_payload_cannot_clear_existing_assignment(self):
        self.assign([self.teacher.pk])
        for payload in [{}, {'maestra_ids': 'all'}, {'maestra_ids':[True]}, {'maestra_ids':[-1]}, []]:
            response = self.client.patch(self.url, payload, format='json', HTTP_X_SCHOOL=self.school.slug)
            self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(IntegrationStudentAssignment.objects.count(), 1)

    def test_non_ppi_and_cross_school_students_are_rejected(self):
        self.assertEqual(self.assign([self.teacher.pk], f'/api/admin/integracion/alumnos/{self.external.pk}').status_code, 404)
        self.student.es_ppi = False
        self.student.save(update_fields=['es_ppi'])
        self.assertEqual(self.assign([self.teacher.pk]).status_code, 404)

    def test_integration_cannot_modify_own_assignment_or_read_admin_overview(self):
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.assign([self.teacher.pk]).status_code, 403)
        self.assertEqual(self.get('/api/admin/integracion/alumnos').status_code, 403)
        self.assertEqual(self.client.get('/api/integracion/alumnos', HTTP_X_SCHOOL=self.other.slug).status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.get('/api/integracion/alumnos').status_code, 401)

    def test_access_is_revoked_if_student_leaves_ppi_or_membership_is_inactive(self):
        self.assign([self.teacher.pk])
        self.client.force_authenticate(self.teacher)
        self.student.es_ppi = False
        self.student.save(update_fields=['es_ppi'])
        self.assertEqual(self.get('/api/integracion/alumnos').data['alumnos'], [])
        self.assertEqual(self.get(f'/api/alumnos/{self.student.pk}/').status_code, 403)
        self.student.es_ppi = True
        self.student.save(update_fields=['es_ppi'])
        SchoolMembership.objects.filter(user=self.teacher).update(is_active=False)
        self.assertEqual(self.get('/api/integracion/alumnos').status_code, 403)

    def test_assignment_stays_with_student_on_course_change_but_not_school_change(self):
        self.assign([self.teacher.pk])
        course = SchoolCourse.objects.create(school=self.school, code='2A', name='2A')
        self.student.school_course = course
        self.student.curso = course.code
        self.student.save()
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.get(f'/api/alumnos/{self.student.pk}/').status_code, 200)
        self.student.school = self.other
        self.student.school_course = self.other_course
        self.student.curso = self.other_course.code
        self.student.save()
        self.assertEqual(self.get('/api/integracion/alumnos').data['alumnos'], [])
        self.assertIn(self.get(f'/api/alumnos/{self.student.pk}/').status_code, [403, 404])

    def test_legacy_migration_preserves_membership_without_assigning_entire_course(self):
        SchoolMembership.objects.filter(user=self.teacher).delete()
        PreceptorCurso.objects.create(preceptor=self.teacher, school=self.school, school_course=self.course, curso='1A')
        migration = import_module('calificaciones.migrations.0103_integration_student_assignments')
        migration.move_integration_to_school(apps, SimpleNamespace(connection=connection))
        self.assertTrue(SchoolMembership.objects.filter(user=self.teacher, school=self.school).exists())
        self.assertFalse(PreceptorCurso.objects.filter(preceptor=self.teacher).exists())
        self.assertFalse(IntegrationStudentAssignment.objects.exists())
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.get('/api/integracion/alumnos').data['alumnos'], [])

    def test_legacy_course_assignment_api_rejects_integration(self):
        response = self.client.patch(f'/api/admin/staff/course/{self.course.pk}/', {'staff_role':'Integracion', 'user_ids':[self.teacher.pk]}, format='json', HTTP_X_SCHOOL=self.school.slug)
        self.assertEqual(response.status_code, 400)
