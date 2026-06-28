from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from calificaciones.models import School, SchoolCourse
from calificaciones.models_preceptores import SchoolAdmin


def _make_user(username: str, *, is_superuser: bool = False):
    return get_user_model().objects.create_user(
        username=username,
        password="test1234",
        is_superuser=is_superuser,
        is_staff=is_superuser,
    )


@override_settings(SECURE_SSL_REDIRECT=False)
class AdminSchoolCoursesApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.school_a = School.objects.create(name="Colegio Norte", slug="colegio-norte")
        self.school_b = School.objects.create(name="Colegio Sur", slug="colegio-sur")
        self.course_a = SchoolCourse.objects.create(
            school=self.school_a,
            code="1A",
            name="1A Norte",
            sort_order=1,
            is_active=True,
        )
        self.course_b = SchoolCourse.objects.create(
            school=self.school_b,
            code="1A",
            name="1A Sur",
            sort_order=1,
            is_active=True,
        )

        self.school_admin_group, _ = Group.objects.get_or_create(name="Administradores")

    def test_superuser_ve_todos_los_colegios(self):
        admin = _make_user("admin_global", is_superuser=True)
        self.client.force_authenticate(user=admin)

        response = self.client.get("/api/admin/school-courses/")

        self.assertEqual(response.status_code, 200)
        slugs = {row["slug"] for row in response.json()["schools"]}
        self.assertTrue({self.school_a.slug, self.school_b.slug}.issubset(slugs))

    def test_admin_de_colegio_solo_ve_su_colegio(self):
        school_admin = _make_user("admin_colegio")
        school_admin.groups.add(self.school_admin_group)
        SchoolAdmin.objects.create(school=self.school_a, admin=school_admin)
        self.client.force_authenticate(user=school_admin)

        response = self.client.get("/api/admin/school-courses/")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["schools"]), 1)
        self.assertEqual(body["schools"][0]["slug"], self.school_a.slug)

    def test_admin_de_colegio_no_puede_crear_en_otro_colegio(self):
        school_admin = _make_user("admin_colegio_create")
        school_admin.groups.add(self.school_admin_group)
        SchoolAdmin.objects.create(school=self.school_a, admin=school_admin)
        self.client.force_authenticate(user=school_admin)

        response = self.client.post(
            f"/api/admin/school-courses/{self.school_b.id}/",
            {"code": "2A", "name": "2A Sur"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(SchoolCourse.objects.filter(school=self.school_b, code="2A").exists())

    def test_admin_de_colegio_no_puede_editar_curso_de_otro_colegio(self):
        school_admin = _make_user("admin_colegio_edit")
        school_admin.groups.add(self.school_admin_group)
        SchoolAdmin.objects.create(school=self.school_a, admin=school_admin)
        self.client.force_authenticate(user=school_admin)

        response = self.client.patch(
            f"/api/admin/school-courses/course/{self.course_b.id}/",
            {"name": "2A Editado"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.course_b.refresh_from_db()
        self.assertEqual(self.course_b.name, "1A Sur")

    def test_admin_de_colegio_puede_crear_en_su_colegio_activo(self):
        school_admin = _make_user("admin_colegio_ok")
        school_admin.groups.add(self.school_admin_group)
        SchoolAdmin.objects.create(school=self.school_a, admin=school_admin)
        self.client.force_authenticate(user=school_admin)

        response = self.client.post(
            f"/api/admin/school-courses/{self.school_a.id}/",
            {"code": "2A", "name": "2A Norte"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(SchoolCourse.objects.filter(school=self.school_a, code="2A").exists())
