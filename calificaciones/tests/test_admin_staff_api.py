from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from calificaciones.models import School, SchoolCourse
from calificaciones.models_preceptores import PreceptorCurso, ProfesorCurso


def _make_user(username: str, *, is_superuser: bool = False):
    return get_user_model().objects.create_user(
        username=username,
        password="test1234",
        is_superuser=is_superuser,
        is_staff=is_superuser,
    )


@override_settings(SECURE_SSL_REDIRECT=False)
class AdminStaffApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = _make_user("admin_staff_tool", is_superuser=True)
        self.client.force_authenticate(user=self.admin)

        self.school = School.objects.create(name="Colegio Norte", slug="colegio-norte")
        self.other_school = School.objects.create(name="Colegio Sur", slug="colegio-sur")

        self.course_a = SchoolCourse.objects.create(
            school=self.school,
            code="1A",
            name="1A Norte",
            sort_order=1,
            is_active=True,
        )
        self.course_b = SchoolCourse.objects.create(
            school=self.school,
            code="1B",
            name="1B Norte",
            sort_order=2,
            is_active=True,
        )
        self.other_course = SchoolCourse.objects.create(
            school=self.other_school,
            code="2A",
            name="2A Sur",
            sort_order=1,
            is_active=True,
        )

        self.prof_group, _ = Group.objects.get_or_create(name="Profesores")
        self.prec_group, _ = Group.objects.get_or_create(name="Preceptores")
        self.dir_group, _ = Group.objects.get_or_create(name="Directivos")

    def test_overview_lista_usuarios_y_asignaciones_del_colegio_activo(self):
        profesor = _make_user("profesor_norte")
        profesor.groups.add(self.prof_group)
        ProfesorCurso.objects.create(
            school=self.school,
            school_course=self.course_a,
            profesor=profesor,
            curso=self.course_a.code,
        )
        ProfesorCurso.objects.create(
            school=self.other_school,
            school_course=self.other_course,
            profesor=profesor,
            curso=self.other_course.code,
        )

        preceptor = _make_user("preceptor_norte")
        preceptor.groups.add(self.prec_group)
        PreceptorCurso.objects.create(
            school=self.school,
            school_course=self.course_b,
            preceptor=preceptor,
            curso=self.course_b.code,
        )

        response = self.client.get("/api/admin/staff/", HTTP_X_SCHOOL=self.school.slug)
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertEqual(body["school"]["slug"], self.school.slug)
        self.assertEqual([course["id"] for course in body["courses"]], [self.course_a.id, self.course_b.id])

        users = {row["username"]: row for row in body["users"]}
        self.assertIn("profesor_norte", users)
        self.assertIn("preceptor_norte", users)
        self.assertEqual(users["profesor_norte"]["staff_role"], "Profesores")
        self.assertEqual(
            [course["id"] for course in users["profesor_norte"]["assigned_school_courses"]],
            [self.course_a.id],
        )
        self.assertEqual(users["preceptor_norte"]["staff_role"], "Preceptores")

    def test_patch_profesor_crea_asignaciones_y_grupo_en_colegio_activo(self):
        docente = _make_user("docente_editable")

        response = self.client.patch(
            f"/api/admin/staff/{docente.id}/",
            {
                "staff_role": "Profesores",
                "school_course_ids": [self.course_a.id, self.course_b.id],
            },
            format="json",
            HTTP_X_SCHOOL=self.school.slug,
        )
        self.assertEqual(response.status_code, 200)
        docente.refresh_from_db()

        self.assertTrue(docente.groups.filter(name="Profesores").exists())
        self.assertEqual(
            list(
                ProfesorCurso.objects.filter(profesor=docente, school=self.school)
                .order_by("school_course__sort_order")
                .values_list("school_course_id", flat=True)
            ),
            [self.course_a.id, self.course_b.id],
        )

    def test_patch_directivo_limpia_asignaciones_del_colegio_activo(self):
        usuario = _make_user("usuario_directivo")
        usuario.groups.add(self.prof_group)
        ProfesorCurso.objects.create(
            school=self.school,
            school_course=self.course_a,
            profesor=usuario,
            curso=self.course_a.code,
        )
        ProfesorCurso.objects.create(
            school=self.other_school,
            school_course=self.other_course,
            profesor=usuario,
            curso=self.other_course.code,
        )

        response = self.client.patch(
            f"/api/admin/staff/{usuario.id}/",
            {
                "staff_role": "Directivos",
                "school_course_ids": [],
            },
            format="json",
            HTTP_X_SCHOOL=self.school.slug,
        )
        self.assertEqual(response.status_code, 200)
        usuario.refresh_from_db()

        self.assertTrue(usuario.groups.filter(name="Directivos").exists())
        self.assertFalse(ProfesorCurso.objects.filter(profesor=usuario, school=self.school).exists())
        self.assertTrue(ProfesorCurso.objects.filter(profesor=usuario, school=self.other_school).exists())

    def test_patch_curso_profesores_actualiza_asignacion_masiva(self):
        profesor_a = _make_user("profesor_a")
        profesor_b = _make_user("profesor_b")
        profesor_c = _make_user("profesor_c")
        profesor_a.groups.add(self.prof_group)
        profesor_b.groups.add(self.prof_group)
        ProfesorCurso.objects.create(
            school=self.school,
            school_course=self.course_a,
            profesor=profesor_a,
            curso=self.course_a.code,
        )

        response = self.client.patch(
            f"/api/admin/staff/course/{self.course_a.id}/",
            {
                "staff_role": "Profesores",
                "user_ids": [profesor_b.id, profesor_c.id],
            },
            format="json",
            HTTP_X_SCHOOL=self.school.slug,
        )
        self.assertEqual(response.status_code, 200)

        assigned_ids = set(
            ProfesorCurso.objects.filter(school=self.school, school_course=self.course_a).values_list("profesor_id", flat=True)
        )
        self.assertEqual(assigned_ids, {profesor_b.id, profesor_c.id})
        self.assertFalse(ProfesorCurso.objects.filter(school=self.school, school_course=self.course_a, profesor=profesor_a).exists())
