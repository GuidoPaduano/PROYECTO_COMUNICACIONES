from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from calificaciones.models import Alumno, Notificacion, Sancion, School, SchoolCourse
from calificaciones.models_preceptores import PreceptorCurso, ProfesorCurso


def _make_user(username: str, groups: list[str] | None = None, *, is_staff: bool = False):
    User = get_user_model()
    user = User.objects.create_user(username=username, password="test1234", is_staff=is_staff)
    for name in groups or []:
        group, _ = Group.objects.get_or_create(name=name)
        user.groups.add(group)
    return user


@override_settings(SECURE_SSL_REDIRECT=False)
class FirmaSancionApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.padre = _make_user("padre_firma_sancion", ["Padres"])
        self.padre_otro = _make_user("padre_otro_sancion", ["Padres"])
        self.alumno = Alumno.objects.create(
            nombre="Eva",
            apellido="Suarez",
            id_alumno="LEG551",
            curso="1A",
            padre=self.padre,
        )
        self.sancion = Sancion.objects.create(
            alumno=self.alumno,
            tipo="Amonestación",
            motivo="Incumplimiento del reglamento",
            fecha="2026-03-11",
            docente="Preceptor 1",
        )

    def test_padre_puede_firmar_sancion_una_vez(self):
        self.client.force_authenticate(user=self.padre)

        res = self.client.post(f"/api/sanciones/{self.sancion.id}/firmar/", format="json")

        self.assertEqual(res.status_code, 200)
        self.sancion.refresh_from_db()
        self.assertTrue(self.sancion.firmada)
        self.assertEqual(self.sancion.firmada_por_id, self.padre.id)
        self.assertIsNotNone(self.sancion.firmada_en)

    def test_padre_no_puede_firmar_sancion_dos_veces(self):
        self.client.force_authenticate(user=self.padre)
        first = self.client.post(f"/api/sanciones/{self.sancion.id}/firmar/", format="json")
        self.assertEqual(first.status_code, 200)

        second = self.client.post(f"/api/sanciones/{self.sancion.id}/firmar/", format="json")

        self.assertEqual(second.status_code, 400)
        self.sancion.refresh_from_db()
        self.assertTrue(self.sancion.firmada)

    def test_otro_padre_no_puede_firmar_sancion(self):
        self.client.force_authenticate(user=self.padre_otro)

        res = self.client.post(f"/api/sanciones/{self.sancion.id}/firmar/", format="json")

        self.assertEqual(res.status_code, 403)
        self.sancion.refresh_from_db()
        self.assertFalse(self.sancion.firmada)


def _make_superuser(username: str):
    User = get_user_model()
    return User.objects.create_user(
        username=username,
        password="test1234",
        is_superuser=True,
        is_staff=True,
    )


@override_settings(SECURE_SSL_REDIRECT=False)
class SancionesSchoolScopingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = _make_superuser("admin_sanciones_school")
        self.preceptor = _make_user("preceptor_sanciones_school", ["Preceptores"])
        self.profesor = _make_user("profesor_sanciones_school", ["Profesores"])
        self.profesor_otro = _make_user("profesor_otro_sanciones_school", ["Profesores"])
        self.profesor_sin_asignacion = _make_user("profesor_sin_asignacion_sanciones", ["Profesores"])
        self.staff_sin_rol = _make_user("staff_sin_rol_sanciones", is_staff=True)
        self.padre = _make_user("padre_sanciones_school", ["Padres"])
        self.school_a = School.objects.create(name="Colegio Sanciones Norte", slug="colegio-sanciones-norte")
        self.school_b = School.objects.create(name="Colegio Sanciones Sur", slug="colegio-sanciones-sur")
        self.school_course_a = SchoolCourse.objects.create(
            school=self.school_a,
            code="1A",
            name="1A Norte",
            sort_order=1,
        )
        self.school_course_b = SchoolCourse.objects.create(
            school=self.school_b,
            code="1A",
            name="1A Sur",
            sort_order=1,
        )
        self.school_course_a_2 = SchoolCourse.objects.create(
            school=self.school_a,
            code="2A",
            name="2A Norte",
            sort_order=2,
        )
        self.alumno_a = Alumno.objects.create(
            school=self.school_a,
            nombre="Nora",
            apellido="Sancion",
            id_alumno="SANC001",
            curso="1A",
            padre=self.padre,
        )
        self.alumno_a_2 = Alumno.objects.create(
            school=self.school_a,
            nombre="Luca",
            apellido="Sancion",
            id_alumno="SANC003",
            curso="2A",
        )
        self.alumno_b = Alumno.objects.create(
            school=self.school_b,
            nombre="Bruno",
            apellido="Sancion",
            id_alumno="SANC002",
            curso="1A",
        )
        self.sancion_a = Sancion.objects.create(
            school=self.school_a,
            alumno=self.alumno_a,
            tipo="AmonestaciÃ³n",
            motivo="Falta leve",
            fecha="2026-03-12",
            docente="Preceptor 1",
        )
        self.sancion_b = Sancion.objects.create(
            school=self.school_b,
            alumno=self.alumno_b,
            tipo="AmonestaciÃ³n",
            motivo="Falta grave",
            fecha="2026-03-13",
            docente="Preceptor 2",
        )
        PreceptorCurso.objects.create(
            school=self.school_a,
            preceptor=self.preceptor,
            curso="1A",
        )
        ProfesorCurso.objects.create(
            school=self.school_a,
            profesor=self.profesor,
            curso="1A",
        )
        ProfesorCurso.objects.create(
            school=self.school_a,
            profesor=self.profesor_otro,
            curso="2A",
        )
        self.client.force_authenticate(user=self.admin)

    def test_lista_filtra_por_school_activo(self):
        res = self.client.get(
            "/api/sanciones/",
            {"school": self.school_a.slug},
        )

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual([item["id"] for item in data["results"]], [self.sancion_a.id])
        self.assertNotIn("curso", data["results"][0])
        self.assertEqual(data["results"][0]["school_course_id"], self.alumno_a.school_course_id)
        self.assertEqual(data["results"][0]["school_course_name"], "1A Norte")

    def test_lista_acepta_school_course_id(self):
        res = self.client.get(
            "/api/sanciones/",
            {
                "school": self.school_a.slug,
                "school_course_id": self.school_course_a.id,
            },
        )

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual([item["id"] for item in data["results"]], [self.sancion_a.id])
        self.assertEqual(data["results"][0]["school_course_id"], self.school_course_a.id)
        self.assertEqual(data["results"][0]["school_course_name"], "1A Norte")

    def test_lista_rechaza_curso_legacy(self):
        res = self.client.get(
            "/api/sanciones/",
            {
                "school": self.school_a.slug,
                "curso": "1A",
            },
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            res.json()["detail"],
            "El parámetro 'curso' está deprecado en este endpoint. Usa school_course_id.",
        )

    def test_detalle_serializa_school_course_sin_curso(self):
        res = self.client.get(
            f"/api/sanciones/{self.sancion_a.id}/",
            {"school": self.school_a.slug},
        )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertNotIn("curso", body)
        self.assertEqual(body["school_course_id"], self.alumno_a.school_course_id)
        self.assertEqual(body["school_course_name"], "1A Norte")

    def test_detalle_no_expone_sancion_de_otro_school(self):
        res = self.client.get(
            f"/api/sanciones/{self.sancion_b.id}/",
            {"school": self.school_a.slug},
        )

        self.assertEqual(res.status_code, 404)

    def test_crear_sancion_asigna_school_y_notificacion(self):
        res = self.client.post(
            f"/api/sanciones/?school={self.school_a.slug}",
            {
                "alumno": self.alumno_a.id,
                "mensaje": "Observacion",
                "asunto": "Disciplina",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 201)
        self.assertNotIn("ok", res.json())
        creada = Sancion.objects.exclude(id__in=[self.sancion_a.id, self.sancion_b.id]).get()
        notif = Notificacion.objects.filter(tipo="sancion").latest("id")
        self.assertEqual(creada.school_id, self.school_a.id)
        self.assertEqual(notif.school_id, self.school_a.id)
        self.assertEqual(notif.meta["school_course_id"], self.alumno_a.school_course_id)
        self.assertEqual(notif.meta["school_course_name"], "1A Norte")
        self.assertNotIn("curso", notif.meta)
        self.assertIn("1A Norte", notif.descripcion)

    def test_preceptor_puede_crear_sancion_en_curso_asignado(self):
        self.client.force_authenticate(user=self.preceptor)

        res = self.client.post(
            "/api/sanciones/",
            {
                "alumno": self.alumno_a.id,
                "mensaje": "Observacion preceptor",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 201)
        self.assertNotIn("ok", res.json())
        self.assertTrue(Sancion.objects.filter(alumno=self.alumno_a, motivo="Observacion preceptor").exists())

    def test_profesor_puede_crear_sancion_en_curso_asignado(self):
        self.client.force_authenticate(user=self.profesor)

        res = self.client.post(
            "/api/sanciones/",
            {
                "alumno": self.alumno_a.id,
                "mensaje": "Observacion profesor",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 201)
        self.assertNotIn("ok", res.json())
        self.assertTrue(Sancion.objects.filter(alumno=self.alumno_a, motivo="Observacion profesor").exists())

    def test_profesor_no_puede_crear_sancion_en_otro_curso(self):
        self.client.force_authenticate(user=self.profesor_otro)

        res = self.client.post(
            "/api/sanciones/",
            {
                "alumno": self.alumno_a.id,
                "mensaje": "Observacion profesor fuera de curso",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No autorizado para ese alumno.")
        self.assertFalse(
            Sancion.objects.filter(alumno=self.alumno_a, motivo="Observacion profesor fuera de curso").exists()
        )

    def test_profesor_sin_asignacion_no_puede_crear_sancion(self):
        self.client.force_authenticate(user=self.profesor_sin_asignacion)

        res = self.client.post(
            "/api/sanciones/",
            {
                "alumno": self.alumno_a.id,
                "mensaje": "Observacion profesor sin asignacion",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No autorizado para ese alumno.")
        self.assertFalse(
            Sancion.objects.filter(alumno=self.alumno_a, motivo="Observacion profesor sin asignacion").exists()
        )

    def test_preceptor_no_puede_crear_sancion_en_otro_curso_del_mismo_colegio(self):
        self.client.force_authenticate(user=self.preceptor)

        res = self.client.post(
            "/api/sanciones/",
            {
                "alumno": self.alumno_a_2.id,
                "mensaje": "Observacion fuera de curso",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No autorizado para ese alumno.")
        self.assertFalse(Sancion.objects.filter(alumno=self.alumno_a_2, motivo="Observacion fuera de curso").exists())

    def test_preceptor_no_puede_eliminar_sancion_de_otro_curso(self):
        sancion_otro_curso = Sancion.objects.create(
            school=self.school_a,
            alumno=self.alumno_a_2,
            tipo="AmonestaciÃƒÂ³n",
            motivo="Interrupcion de clase",
            fecha="2026-03-14",
            docente="Preceptor 3",
        )
        self.client.force_authenticate(user=self.preceptor)

        res = self.client.delete(f"/api/sanciones/{sancion_otro_curso.id}/")

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No autorizado para ese alumno.")
        self.assertTrue(Sancion.objects.filter(id=sancion_otro_curso.id).exists())

    def test_staff_sin_rol_no_puede_crear_sancion(self):
        self.client.force_authenticate(user=self.staff_sin_rol)

        res = self.client.post(
            "/api/sanciones/",
            {
                "alumno": self.alumno_a.id,
                "mensaje": "Observacion staff sin rol",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No autorizado.")
        self.assertFalse(Sancion.objects.filter(alumno=self.alumno_a, motivo="Observacion staff sin rol").exists())

    def test_staff_sin_rol_no_puede_eliminar_sancion(self):
        self.client.force_authenticate(user=self.staff_sin_rol)

        res = self.client.delete(f"/api/sanciones/{self.sancion_a.id}/")

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No autorizado.")
        self.assertTrue(Sancion.objects.filter(id=self.sancion_a.id).exists())
