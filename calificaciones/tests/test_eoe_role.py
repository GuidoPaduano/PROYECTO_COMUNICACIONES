from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from calificaciones.models import Alumno, Asistencia, Evento, Mensaje, Nota, Sancion, School, SchoolCourse
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

    def test_message_recipient_roster_and_send_are_limited_to_ppi_students(self):
        user = self.create_eoe()
        student_user = get_user_model().objects.create_user(username='ppi_message_student')
        regular_user = get_user_model().objects.create_user(username='regular_message_student')
        ppi = Alumno.objects.create(
            school=self.school, school_course=self.course, curso='1A',
            id_alumno='PPI-MSG', nombre='Ana', es_ppi=True, usuario=student_user,
        )
        regular = Alumno.objects.create(
            school=self.school, school_course=self.course, curso='1A',
            id_alumno='REG-MSG', nombre='Otra', es_ppi=False, usuario=regular_user,
        )
        self.client.force_authenticate(user)
        headers = {'HTTP_X_SCHOOL': self.school.slug}
        roster = self.client.get(f'/api/alumnos/?school_course_id={self.course.id}', **headers)
        self.assertEqual(roster.status_code, 200, roster.data)
        self.assertEqual([row['id'] for row in roster.data['alumnos']], [ppi.id])
        path_roster = self.client.get(f'/api/alumnos/curso/{self.course.id}/', **headers)
        self.assertEqual(path_roster.status_code, 200, path_roster.data)
        self.assertEqual([row['id'] for row in path_roster.data['alumnos']], [ppi.id])

        sent = self.client.post('/api/mensajes/enviar/', {
            'alumno_id': ppi.id, 'contenido': 'Consulta PPI',
        }, format='json', **headers)
        self.assertEqual(sent.status_code, 201, sent.data)
        self.assertTrue(Mensaje.objects.filter(remitente=user, destinatario=student_user, alumno=ppi).exists())
        denied = self.client.post('/api/mensajes/enviar/', {
            'alumno_id': regular.id, 'contenido': 'Consulta regular',
        }, format='json', **headers)
        self.assertEqual(denied.status_code, 403, denied.data)
        group_sent = self.client.post('/api/mensajes/enviar_grupal/', {
            'school_course_id': self.course.id, 'contenido': 'Aviso PPI',
        }, format='json', **headers)
        self.assertEqual(group_sent.status_code, 201, group_sent.data)
        self.assertFalse(Mensaje.objects.filter(remitente=user, destinatario=regular_user).exists())

        SchoolMembership.objects.filter(user=user, school=self.school).update(is_active=False)
        self.assertEqual(self.client.get(f'/api/alumnos/?school_course_id={self.course.id}', **headers).status_code, 403)
        self.assertEqual(self.client.post('/api/mensajes/enviar/', {
            'alumno_id': ppi.id, 'contenido': 'Sin membresía',
        }, format='json', **headers).status_code, 403)

    def test_course_assignment_rejected(self):
        user = self.create_eoe()
        response = self.client.patch(f'/api/admin/staff/course/{self.course.id}/', {'staff_role':'EOE', 'user_ids':[user.id]}, format='json', HTTP_X_SCHOOL=self.school.slug)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(PreceptorCurso.objects.filter(preceptor=user).exists())

    def test_calendar_shows_every_course_in_own_school_without_assignments(self):
        user = self.create_eoe()
        own_events = [
            Evento.objects.create(school=self.school, school_course=course, curso=course.code, titulo=f'Evento {course.code}', fecha='2026-10-20')
            for course in [self.course, self.other]
        ]
        external_course = SchoolCourse.objects.create(school=self.other_school, code='1A', name='1A')
        Evento.objects.create(school=self.other_school, school_course=external_course, curso='1A', titulo='Otro colegio', fecha='2026-10-20')
        self.client.force_authenticate(user)
        courses = self.client.get('/api/preceptor/cursos/', HTTP_X_SCHOOL=self.school.slug)
        self.assertEqual(courses.status_code, 200, courses.data)
        self.assertEqual({course['school_course_id'] for course in courses.data['cursos']}, {self.course.id, self.other.id})
        events = self.client.get('/api/eventos/', HTTP_X_SCHOOL=self.school.slug)
        self.assertEqual(events.status_code, 200, events.data)
        self.assertEqual({event['id'] for event in events.data}, {str(event.id) for event in own_events})
        filtered = self.client.get(f'/api/eventos/?school_course_id={self.other.id}', HTTP_X_SCHOOL=self.school.slug)
        self.assertEqual([event['id'] for event in filtered.data], [str(own_events[1].id)])
        self.assertEqual(self.client.get('/api/eventos/', HTTP_X_SCHOOL=self.other_school.slug).status_code, 403)
        self.assertFalse(PreceptorCurso.objects.filter(preceptor=user).exists())

    def test_can_read_ppi_grades_attendance_and_sanctions_across_courses(self):
        user = self.create_eoe()
        students = [
            Alumno.objects.create(
                school=self.school, school_course=course, curso=course.code,
                id_alumno=f'PPI-READ-{course.code}', nombre='Ana', es_ppi=True,
            )
            for course in (self.course, self.other)
        ]
        for student in students:
            Nota.objects.create(alumno=student, school=self.school, materia='Matemática', tipo='Examen',
                                calificacion='8', cuatrimestre=1)
            Asistencia.objects.create(alumno=student, school=self.school, fecha='2026-10-19',
                                      tipo_asistencia='clases', presente=False)
            Sancion.objects.create(alumno=student, school=self.school, motivo='Prueba de lectura')

        self.client.force_authenticate(user)
        for student in students:
            routes = (
                (f'/api/notas/?alumno={student.id}', 'notas'),
                (f'/api/alumnos/{student.id}/notas/', 'notas'),
                (f'/api/asistencias/?alumno={student.id}', 'results'),
                (f'/api/sanciones/?alumno={student.id}', 'results'),
            )
            for path, key in routes:
                response = self.client.get(path, HTTP_X_SCHOOL=self.school.slug)
                self.assertEqual(response.status_code, 200, (path, response.data))
                self.assertEqual(len(response.data[key]), 1, path)
        self.assertFalse(PreceptorCurso.objects.filter(preceptor=user).exists())

    def test_ppi_read_access_stays_within_active_school_and_ppi_students(self):
        user = self.create_eoe()
        regular = Alumno.objects.create(school=self.school, school_course=self.course, curso='1A',
                                        id_alumno='NON-PPI-READ', nombre='Otra', es_ppi=False)
        external_course = SchoolCourse.objects.create(school=self.other_school, code='2A', name='2A')
        external = Alumno.objects.create(school=self.other_school, school_course=external_course,
                                         curso='2A', id_alumno='OTHER-PPI-READ', nombre='Externa', es_ppi=True)
        ppi = Alumno.objects.create(school=self.school, school_course=self.course, curso='1A',
                                    id_alumno='OWN-PPI-READ', nombre='Ana', es_ppi=True)
        self.client.force_authenticate(user)
        paths = (
            lambda student: f'/api/notas/?alumno={student.id}',
            lambda student: f'/api/alumnos/{student.id}/notas/',
            lambda student: f'/api/asistencias/?alumno={student.id}',
            lambda student: f'/api/sanciones/?alumno={student.id}',
        )
        for path in paths:
            self.assertEqual(self.client.get(path(regular), HTTP_X_SCHOOL=self.school.slug).status_code, 403)
            self.assertEqual(self.client.get(path(external), HTTP_X_SCHOOL=self.school.slug).status_code, 404)
        SchoolMembership.objects.filter(user=user, school=self.school).update(is_active=False)
        for path in paths:
            self.assertEqual(self.client.get(path(ppi), HTTP_X_SCHOOL=self.school.slug).status_code, 403)

    def test_teacher_cannot_open_eoe_roster(self):
        from django.contrib.auth.models import Group
        user = get_user_model().objects.create_user(username='teacher')
        user.groups.add(Group.objects.get_or_create(name='Profesores')[0])
        SchoolMembership.objects.create(school=self.school,user=user)
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get('/api/eoe/alumnos', HTTP_X_SCHOOL=self.school.slug).status_code, 403)
