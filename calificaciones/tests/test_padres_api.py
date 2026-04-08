from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from calificaciones.models import Alumno, Nota, School, SchoolCourse


def _make_superuser(username: str):
    User = get_user_model()
    return User.objects.create_user(
        username=username,
        password="test1234",
        is_superuser=True,
        is_staff=True,
    )


@override_settings(SECURE_SSL_REDIRECT=False)
class PadresSchoolScopingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = _make_superuser("admin_padres_school")
        self.school_a = School.objects.create(name="Colegio Padres Norte", slug="colegio-padres-norte")
        self.school_b = School.objects.create(name="Colegio Padres Sur", slug="colegio-padres-sur")
        SchoolCourse.objects.create(school=self.school_a, code="1A", name="1A Norte", sort_order=1)
        SchoolCourse.objects.create(school=self.school_b, code="1A", name="1A Sur", sort_order=1)
        self.alumno_a = Alumno.objects.create(
            school=self.school_a,
            nombre="Ana",
            apellido="Padres",
            id_alumno="PAD001",
            curso="1A",
        )
        self.alumno_b = Alumno.objects.create(
            school=self.school_b,
            nombre="Beto",
            apellido="Padres",
            id_alumno="PAD002",
            curso="1A",
        )
        self.nota_a = Nota.objects.create(
            school=self.school_a,
            alumno=self.alumno_a,
            materia="Lengua",
            tipo="Examen",
            calificacion="8",
            cuatrimestre=1,
        )
        Nota.objects.create(
            school=self.school_b,
            alumno=self.alumno_b,
            materia="Lengua",
            tipo="Examen",
            calificacion="6",
            cuatrimestre=1,
        )
        self.client.force_authenticate(user=self.admin)

    def test_mis_hijos_filtra_por_school_activo(self):
        res = self.client.get(
            "/api/padres/mis-hijos/",
            {"school": self.school_a.slug},
        )

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertNotIn("ok", data)
        self.assertEqual([item["id_alumno"] for item in data["results"]], [self.alumno_a.id_alumno])
        self.assertNotIn("curso", data["results"][0])
        self.assertEqual(data["results"][0]["school_course_id"], self.alumno_a.school_course_id)
        self.assertEqual(data["results"][0]["school_course_name"], "1A Norte")

    def test_notas_de_hijo_no_expone_alumno_de_otro_school(self):
        res = self.client.get(
            f"/api/padres/hijos/{self.alumno_b.id_alumno}/notas/",
            {"school": self.school_a.slug},
        )

        self.assertEqual(res.status_code, 404)

    def test_notas_de_hijo_lista_solo_notas_del_school_activo(self):
        res = self.client.get(
            f"/api/padres/hijos/{self.alumno_a.id_alumno}/notas/",
            {"school": self.school_a.slug},
        )

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertNotIn("ok", data)
        self.assertEqual([item["id"] for item in data["results"]], [self.nota_a.id])
        self.assertNotIn("curso", data["alumno"])
        self.assertEqual(data["alumno"]["school_course_id"], self.alumno_a.school_course_id)
        self.assertEqual(data["alumno"]["school_course_name"], "1A Norte")
