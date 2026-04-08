from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from calificaciones.models import Alumno, School, SchoolCourse
from calificaciones.models_preceptores import PreceptorCurso, ProfesorCurso


def _make_user(username: str, groups: list[str] | None = None, *, is_superuser: bool = False):
    User = get_user_model()
    user = User.objects.create_user(
        username=username,
        password="test1234",
        is_superuser=is_superuser,
        is_staff=is_superuser,
    )
    for group_name in groups or []:
        group, _ = Group.objects.get_or_create(name=group_name)
        user.groups.add(group)
    return user


@override_settings(SECURE_SSL_REDIRECT=False)
class LegacyCourseNavigationApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = _make_user("admin_legacy_course_nav", is_superuser=True)
        self.preceptor = _make_user("preceptor_legacy_course_nav", ["Preceptores"])
        self.preceptor_sin_asignacion = _make_user("preceptor1", ["Preceptores"])
        self.profesor = _make_user("profesor_legacy_course_nav", ["Profesores"])
        self.profesor_sin_asignacion = _make_user("profesor_legacy_course_nav_sin_asignacion", ["Profesores"])
        self.alumno_user = _make_user("alumno_legacy_course_nav", ["Alumnos"])
        self.school_a = School.objects.create(name="Colegio Legacy Norte", slug="colegio-legacy-norte")
        self.school_b = School.objects.create(name="Colegio Legacy Sur", slug="colegio-legacy-sur")
        self.course_a1 = SchoolCourse.objects.create(
            school=self.school_a,
            code="1A",
            name="1A Norte",
            sort_order=1,
        )
        self.course_a2 = SchoolCourse.objects.create(
            school=self.school_a,
            code="2A",
            name="2A Norte",
            sort_order=2,
        )
        self.course_b1 = SchoolCourse.objects.create(
            school=self.school_b,
            code="1A",
            name="1A Sur",
            sort_order=1,
        )
        PreceptorCurso.objects.create(
            school=self.school_a,
            preceptor=self.preceptor,
            curso="1A",
        )
        ProfesorCurso.objects.create(
            school=self.school_b,
            profesor=self.profesor,
            curso="1A",
        )
        ProfesorCurso.objects.create(
            school=self.school_a,
            profesor=self.profesor,
            curso="2A",
        )
        self.alumno_a1 = Alumno.objects.create(
            school=self.school_a,
            nombre="Ana",
            apellido="Legacy",
            id_alumno="LEGNAV001",
            curso="1A",
            usuario=self.alumno_user,
        )
        self.alumno_a2 = Alumno.objects.create(
            school=self.school_a,
            nombre="Bruno",
            apellido="Legacy",
            id_alumno="LEGNAV002",
            curso="2A",
        )
        Alumno.objects.create(
            school=self.school_b,
            nombre="Carla",
            apellido="Legacy",
            id_alumno="LEGNAV003",
            curso="1A",
        )

    def test_mi_curso_incluye_school_course_contexto(self):
        self.client.force_authenticate(user=self.alumno_user)

        res = self.client.get("/api/mi-curso/", {"school": self.school_a.slug})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            res.json(),
            {
                "school_course_id": self.course_a1.id,
                "school_course_name": "1A Norte",
            },
        )

    def test_superuser_mi_curso_acepta_school_course_id(self):
        self.client.force_authenticate(user=self.admin)

        res = self.client.get(
            "/api/mi-curso/",
            {"school": self.school_a.slug, "school_course_id": self.course_a2.id},
        )

        self.assertEqual(res.status_code, 200)
        self.assertNotIn("curso", res.json())
        self.assertEqual(res.json()["school_course_id"], self.course_a2.id)
        self.assertEqual(res.json()["school_course_name"], "2A Norte")

    def test_superuser_mi_curso_rechaza_curso_legacy(self):
        self.client.force_authenticate(user=self.admin)

        res = self.client.get(
            "/api/mi-curso/",
            {"school": self.school_a.slug, "curso": "2A"},
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            res.json()["detail"],
            "El parámetro 'curso' está deprecado en este endpoint. Usa school_course_id.",
        )

    def test_preceptor_mi_curso_incluye_school_course_contexto(self):
        self.client.force_authenticate(user=self.preceptor)

        res = self.client.get("/api/mi-curso/", {"school": self.school_a.slug})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            res.json(),
            {
                "school_course_id": self.course_a1.id,
                "school_course_name": "1A Norte",
            },
        )

    def test_preceptor_mi_curso_rechaza_curso_legacy(self):
        self.client.force_authenticate(user=self.preceptor)

        res = self.client.get(
            "/api/mi-curso/",
            {"school": self.school_a.slug, "curso": "1A"},
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            res.json()["detail"],
            "El parámetro 'curso' está deprecado en este endpoint. Usa school_course_id.",
        )

    def test_preceptor_sin_asignacion_no_usa_fallback_hardcodeado(self):
        self.client.force_authenticate(user=self.preceptor_sin_asignacion)

        res = self.client.get("/api/mi-curso/", {"school": self.school_a.slug})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            res.json(),
            {
                "detail": "No se pudo resolver el curso para este usuario.",
                "school_course_id": None,
                "school_course_name": None,
            },
        )

    def test_notas_catalogos_incluye_school_course_id(self):
        self.client.force_authenticate(user=self.admin)

        res = self.client.get("/api/notas/catalogos/", {"school": self.school_a.slug})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            res.json()["cursos"],
            [
                {"id": "1A", "code": "1A", "nombre": "1A Norte", "school_course_id": self.course_a1.id},
                {"id": "2A", "code": "2A", "nombre": "2A Norte", "school_course_id": self.course_a2.id},
            ],
        )

    def test_notas_catalogos_profesor_respeta_school_activo(self):
        self.client.force_authenticate(user=self.profesor)

        res = self.client.get("/api/notas/catalogos/")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            res.json()["cursos"],
            [
                {"id": "2A", "code": "2A", "nombre": "2A Norte", "school_course_id": self.course_a2.id},
            ],
        )

    def test_notas_catalogos_profesor_sin_asignacion_devuelve_vacio(self):
        self.client.force_authenticate(user=self.profesor_sin_asignacion)

        res = self.client.get("/api/notas/catalogos/")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["cursos"], [])

    def test_preceptor_cursos_incluye_school_course_id(self):
        self.client.force_authenticate(user=self.preceptor)

        res = self.client.get("/api/preceptor/cursos/", {"school": self.school_a.slug})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            res.json(),
            {
                "cursos": [
                    {"id": "1A", "code": "1A", "nombre": "1A Norte", "school_course_id": self.course_a1.id},
                ]
            },
        )

    def test_alumnos_por_curso_acepta_school_course_id(self):
        self.client.force_authenticate(user=self.preceptor)

        res = self.client.get(
            "/api/alumnos/",
            {"school": self.school_a.slug, "school_course_id": self.course_a1.id},
        )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertNotIn("curso", body)
        self.assertEqual(body["school_course_id"], self.course_a1.id)
        self.assertEqual(body["school_course_name"], "1A Norte")
        self.assertEqual([item["id"] for item in body["alumnos"]], [self.alumno_a1.id])
        self.assertNotIn("curso", body["alumnos"][0])

    def test_alumnos_por_curso_rechaza_curso_legacy(self):
        self.client.force_authenticate(user=self.preceptor)

        res = self.client.get(
            "/api/alumnos/",
            {"school": self.school_a.slug, "curso": "1A"},
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            res.json()["detail"],
            "El parámetro 'curso' está deprecado en este endpoint. Usa school_course_id.",
        )

    def test_alumnos_por_curso_path_acepta_school_course_id_numerico(self):
        self.client.force_authenticate(user=self.preceptor)

        res = self.client.get(
            f"/api/alumnos/curso/{self.course_a1.id}/",
            {"school": self.school_a.slug},
        )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertNotIn("curso", body)
        self.assertEqual(body["school_course_id"], self.course_a1.id)
        self.assertEqual(body["school_course_name"], "1A Norte")
        self.assertEqual([item["id"] for item in body["alumnos"]], [self.alumno_a1.id])
        self.assertNotIn("curso", body["alumnos"][0])

    def test_alumnos_por_curso_path_rechaza_codigo_legacy(self):
        self.client.force_authenticate(user=self.preceptor)

        res = self.client.get(
            "/api/alumnos/curso/1A/",
            {"school": self.school_a.slug},
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            res.json()["detail"],
            "El código legacy de curso en la ruta está deprecado. Usa school_course_id.",
        )

    def test_alumno_detalle_serializa_school_course_sin_curso(self):
        self.client.force_authenticate(user=self.preceptor)

        res = self.client.get(
            f"/api/alumnos/{self.alumno_a1.id}/",
            {"school": self.school_a.slug},
        )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertNotIn("curso", body)
        self.assertEqual(body["school_course_id"], self.course_a1.id)
        self.assertEqual(body["school_course_name"], "1A Norte")

    def test_profesor_alumno_detalle_prioriza_school_course_sobre_curso_legacy(self):
        Alumno.objects.filter(pk=self.alumno_a2.pk).update(
            school_course=self.course_a2,
            curso="1A",
        )
        self.client.force_authenticate(user=self.profesor)

        res = self.client.get(
            f"/api/alumnos/{self.alumno_a2.id}/",
            {"school": self.school_a.slug},
        )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["school_course_id"], self.course_a2.id)
        self.assertEqual(body["school_course_name"], "2A Norte")
