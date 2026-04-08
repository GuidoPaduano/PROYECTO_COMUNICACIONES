from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.test import Client
from rest_framework.test import APIClient

from calificaciones.models import Alumno, Nota, Notificacion, School, SchoolCourse
from calificaciones.models_preceptores import PreceptorCurso, ProfesorCurso


def _make_user(username: str, groups: list[str] | None = None, *, is_superuser: bool = False):
    User = get_user_model()
    user = User.objects.create_user(
        username=username,
        password="test1234",
        is_superuser=is_superuser,
        is_staff=is_superuser,
    )
    for name in groups or []:
        group, _ = Group.objects.get_or_create(name=name)
        user.groups.add(group)
    return user


@override_settings(SECURE_SSL_REDIRECT=False)
class EditarNotaApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.profesor = _make_user("profe_editor", ["Profesores"])
        self.profesor_otro = _make_user("profe_otro", ["Profesores"])
        self.alumno = Alumno.objects.create(
            nombre="Luz",
            apellido="Perez",
            id_alumno="LEG777",
            curso="1A",
        )
        ProfesorCurso.objects.create(profesor=self.profesor, curso="1A")
        ProfesorCurso.objects.create(profesor=self.profesor_otro, curso="2A")
        self.nota = Nota.objects.create(
            alumno=self.alumno,
            materia="Lengua",
            tipo="Examen",
            calificacion="TEA",
            resultado="TEA",
            cuatrimestre=1,
            fecha="2026-03-01",
            observaciones="Primera version",
        )

    def test_profesor_puede_editar_nota_de_su_curso(self):
        self.client.force_authenticate(user=self.profesor)
        payload = {
            "resultado": "TEP",
            "calificacion": "TEP",
            "nota_numerica": "4.50",
            "observaciones": "Corregida",
        }

        res = self.client.patch(f"/api/calificaciones/notas/{self.nota.id}/", payload, format="json")

        self.assertEqual(res.status_code, 200)
        self.nota.refresh_from_db()
        self.assertEqual(self.nota.resultado, "TEP")
        self.assertEqual(str(self.nota.nota_numerica), "4.50")
        self.assertEqual(self.nota.observaciones, "Corregida")

    def test_profesor_no_puede_editar_nota_de_otro_curso(self):
        self.client.force_authenticate(user=self.profesor_otro)

        res = self.client.patch(
            f"/api/calificaciones/notas/{self.nota.id}/",
            {"calificacion": "TED", "resultado": "TED"},
            format="json",
        )

        self.assertEqual(res.status_code, 403)
        self.nota.refresh_from_db()
        self.assertEqual(self.nota.calificacion, "TEA")


@override_settings(SECURE_SSL_REDIRECT=False)
class CrearNotaPermisosApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.profesor = _make_user("profe_crea_nota", ["Profesores"])
        self.profesor_otro = _make_user("profe_crea_nota_otro", ["Profesores"])
        self.school = School.objects.create(name="Colegio Crear Nota", slug="colegio-crear-nota")
        SchoolCourse.objects.create(school=self.school, code="1A", name="1A Norte", sort_order=1)
        SchoolCourse.objects.create(school=self.school, code="2A", name="2A Norte", sort_order=2)
        self.alumno = Alumno.objects.create(
            school=self.school,
            nombre="Tina",
            apellido="Sosa",
            id_alumno="LEGCN01",
            curso="1A",
        )
        ProfesorCurso.objects.create(school=self.school, profesor=self.profesor, curso="1A")
        ProfesorCurso.objects.create(school=self.school, profesor=self.profesor_otro, curso="2A")

    def test_profesor_no_puede_crear_nota_para_alumno_de_otro_curso(self):
        self.client.force_authenticate(user=self.profesor_otro)

        res = self.client.post(
            "/api/calificaciones/notas/",
            {
                "alumno": self.alumno.id,
                "materia": "Lengua",
                "tipo": "Examen",
                "resultado": "TEA",
                "calificacion": "TEA",
                "cuatrimestre": 1,
                "fecha": "2026-03-12",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No tenés permiso para cargar notas para ese alumno.")
        self.assertFalse(Nota.objects.filter(alumno=self.alumno, materia="Lengua").exists())

    def test_profesor_no_puede_crear_notas_masivas_para_otro_curso(self):
        self.client.force_authenticate(user=self.profesor_otro)

        res = self.client.post(
            "/api/calificaciones/notas/masivo/",
            {
                "notas": [
                    {
                        "alumno": self.alumno.id,
                        "materia": "Lengua",
                        "tipo": "Examen",
                        "resultado": "TEA",
                        "calificacion": "TEA",
                        "cuatrimestre": 1,
                        "fecha": "2026-03-12",
                    }
                ]
            },
            format="json",
        )

        self.assertEqual(res.status_code, 400)
        body = res.json()
        self.assertNotIn("ok", body)
        self.assertEqual(
            body["errors"][0]["errors"]["alumno"],
            ["No tenés permiso para cargar notas para ese alumno."],
        )
        self.assertFalse(Nota.objects.filter(alumno=self.alumno, materia="Lengua").exists())


@override_settings(SECURE_SSL_REDIRECT=False)
class AccessControlSecurityTests(TestCase):
    def setUp(self):
        self.api_client = APIClient()
        self.web_client = Client()
        self.profesor = _make_user("profe_roster", ["Profesores"])
        self.preceptor = _make_user("preceptor_roster", ["Preceptores"])
        self.padre = _make_user("padre_roster", ["Padres"])
        self.padre_otro = _make_user("padre_otro", ["Padres"])
        self.alumno_user = _make_user("alumno_roster", ["Alumnos"])
        self.school = School.objects.create(name="Colegio Roster", slug="colegio-roster")
        self.school_course = SchoolCourse.objects.create(
            school=self.school,
            code="1A",
            name="1A Roster",
            sort_order=1,
        )
        self.alumno = Alumno.objects.create(
            nombre="Ana",
            apellido="Lopez",
            id_alumno="LEG900",
            school=self.school,
            school_course=self.school_course,
            curso="1A",
            padre=self.padre,
            usuario=self.alumno_user,
        )
        ProfesorCurso.objects.create(
            profesor=self.profesor,
            school=self.school,
            school_course=self.school_course,
            curso="1A",
        )
        PreceptorCurso.objects.create(
            preceptor=self.preceptor,
            school=self.school,
            school_course=self.school_course,
            curso="1A",
        )

    def test_padre_no_puede_listar_alumnos_de_un_curso(self):
        self.api_client.force_authenticate(user=self.padre)

        res = self.api_client.get("/api/alumnos/", {"school_course_id": self.school_course.id})

        self.assertEqual(res.status_code, 403)

    def test_preceptor_puede_listar_alumnos_de_su_curso(self):
        self.api_client.force_authenticate(user=self.preceptor)

        res = self.api_client.get("/api/alumnos/", {"school_course_id": self.school_course.id})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["alumnos"]), 1)

    def test_padre_no_puede_descargar_boletin_de_otro_alumno(self):
        self.web_client.force_login(self.padre_otro)

        res = self.web_client.get(f"/boletin/{self.alumno.id_alumno}/")

        self.assertEqual(res.status_code, 403)

    def test_padre_titular_puede_descargar_boletin(self):
        self.web_client.force_login(self.padre)

        res = self.web_client.get(f"/boletin/{self.alumno.id_alumno}/")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "application/pdf")


@override_settings(SECURE_SSL_REDIRECT=False)
class FirmaNotaApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.padre = _make_user("padre_firma_nota", ["Padres"])
        self.padre_otro = _make_user("padre_firma_otro", ["Padres"])
        self.alumno = Alumno.objects.create(
            nombre="Mora",
            apellido="Gimenez",
            id_alumno="LEG333",
            curso="1A",
            padre=self.padre,
        )
        self.nota = Nota.objects.create(
            alumno=self.alumno,
            materia="Lengua",
            tipo="Examen",
            calificacion="8",
            cuatrimestre=1,
            fecha="2026-03-10",
        )

    def test_padre_puede_firmar_nota_una_vez(self):
        self.client.force_authenticate(user=self.padre)

        res = self.client.post(f"/api/notas/{self.nota.id}/firmar/", format="json")

        self.assertEqual(res.status_code, 200)
        self.nota.refresh_from_db()
        self.assertTrue(self.nota.firmada)
        self.assertEqual(self.nota.firmada_por_id, self.padre.id)
        self.assertIsNotNone(self.nota.firmada_en)

    def test_padre_no_puede_firmar_nota_dos_veces(self):
        self.client.force_authenticate(user=self.padre)
        first = self.client.post(f"/api/notas/{self.nota.id}/firmar/", format="json")
        self.assertEqual(first.status_code, 200)

        second = self.client.post(f"/api/notas/{self.nota.id}/firmar/", format="json")

        self.assertEqual(second.status_code, 400)
        self.nota.refresh_from_db()
        self.assertTrue(self.nota.firmada)

    def test_otro_padre_no_puede_firmar_nota(self):
        self.client.force_authenticate(user=self.padre_otro)

        res = self.client.post(f"/api/notas/{self.nota.id}/firmar/", format="json")

        self.assertEqual(res.status_code, 403)
        self.nota.refresh_from_db()
        self.assertFalse(self.nota.firmada)


@override_settings(SECURE_SSL_REDIRECT=False)
class NotasSchoolScopingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = _make_user("admin_notas_school", is_superuser=True)
        self.school_a = School.objects.create(name="Colegio Norte", slug="colegio-norte")
        self.school_b = School.objects.create(name="Colegio Sur", slug="colegio-sur")
        SchoolCourse.objects.create(school=self.school_a, code="1A", name="1A Norte", sort_order=1)
        SchoolCourse.objects.create(school=self.school_b, code="1A", name="1A Sur", sort_order=1)
        self.alumno_a = Alumno.objects.create(
            school=self.school_a,
            nombre="Aina",
            apellido="Perez",
            id_alumno="LEGN01",
            curso="1A",
        )
        self.alumno_b = Alumno.objects.create(
            school=self.school_b,
            nombre="Bruno",
            apellido="Lopez",
            id_alumno="LEGS01",
            curso="1A",
        )
        self.client.force_authenticate(user=self.admin)

    def test_datos_iniciales_nueva_nota_filtra_alumnos_por_school(self):
        res = self.client.get(
            "/api/calificaciones/nueva-nota/datos/",
            {"school_course_id": self.alumno_a.school_course_id, "school": self.school_a.slug},
        )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        alumnos = body["alumnos"]
        self.assertEqual([a["id"] for a in alumnos], [self.alumno_a.id])
        self.assertNotIn("curso", alumnos[0])
        self.assertEqual(alumnos[0]["school_course_id"], self.alumno_a.school_course_id)
        self.assertEqual(alumnos[0]["school_course_name"], "1A Norte")
        self.assertEqual(body["cursos"], [{"id": "1A", "code": "1A", "nombre": "1A Norte", "school_course_id": self.alumno_a.school_course_id}])
        self.assertNotIn("curso_inicial", body)
        self.assertEqual(body["school_course_id_inicial"], self.alumno_a.school_course_id)
        self.assertEqual(body["school_course_name_inicial"], "1A Norte")

    def test_datos_iniciales_nueva_nota_rechaza_curso_legacy(self):
        res = self.client.get(
            "/api/calificaciones/nueva-nota/datos/",
            {"curso": "1A", "school": self.school_a.slug},
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            res.json()["detail"],
            "El parámetro 'curso' está deprecado en este endpoint. Usa school_course_id.",
        )

    def test_datos_iniciales_nueva_nota_acepta_school_course_id(self):
        res = self.client.get(
            "/api/calificaciones/nueva-nota/datos/",
            {"school_course_id": self.alumno_a.school_course_id, "school": self.school_a.slug},
        )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual([a["id"] for a in body["alumnos"]], [self.alumno_a.id])
        self.assertNotIn("curso_inicial", body)
        self.assertEqual(body["school_course_id_inicial"], self.alumno_a.school_course_id)
        self.assertEqual(body["school_course_name_inicial"], "1A Norte")


@override_settings(SECURE_SSL_REDIRECT=False)
class NotasReadSchoolScopingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.profesor = _make_user("profe_notas_school_read", ["Profesores"])
        self.profesor_otro_curso = _make_user("profe_notas_otro_curso", ["Profesores"])
        self.school_a = School.objects.create(name="Colegio Notas Norte", slug="colegio-notas-norte")
        self.school_b = School.objects.create(name="Colegio Notas Sur", slug="colegio-notas-sur")
        SchoolCourse.objects.create(school=self.school_a, code="1A", name="1A Norte", sort_order=1)
        SchoolCourse.objects.create(school=self.school_a, code="2A", name="2A Norte", sort_order=2)
        SchoolCourse.objects.create(school=self.school_b, code="1A", name="1A Sur", sort_order=1)
        self.alumno_a = Alumno.objects.create(
            school=self.school_a,
            nombre="Eva",
            apellido="Diaz",
            id_alumno="LEGNR1",
            curso="1A",
        )
        self.alumno_b = Alumno.objects.create(
            school=self.school_b,
            nombre="Gael",
            apellido="Ruiz",
            id_alumno="LEGSR1",
            curso="1A",
        )
        ProfesorCurso.objects.create(
            school=self.school_a,
            profesor=self.profesor,
            curso="1A",
        )
        ProfesorCurso.objects.create(
            school=self.school_a,
            profesor=self.profesor_otro_curso,
            curso="2A",
        )
        Nota.objects.create(
            school=self.school_a,
            alumno=self.alumno_a,
            materia="Lengua",
            tipo="Examen",
            calificacion="8",
            cuatrimestre=1,
            fecha="2026-03-10",
        )
        Nota.objects.create(
            school=self.school_b,
            alumno=self.alumno_b,
            materia="Lengua",
            tipo="Examen",
            calificacion="7",
            cuatrimestre=1,
            fecha="2026-03-10",
        )
        self.client.force_authenticate(user=self.profesor)

    def test_profesor_puede_leer_notas_de_su_school(self):
        res = self.client.get("/api/notas/", {"alumno": self.alumno_a.id})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["alumno"]["id"], self.alumno_a.id)

    def test_profesor_no_puede_leer_alumno_homologo_de_otro_school(self):
        res = self.client.get("/api/notas/", {"alumno": self.alumno_b.id})

        self.assertEqual(res.status_code, 404)

    def test_profesor_no_puede_leer_alumno_de_otro_curso_en_mismo_school(self):
        self.client.force_authenticate(user=self.profesor_otro_curso)

        res = self.client.get("/api/notas/", {"alumno": self.alumno_a.id})

        self.assertEqual(res.status_code, 403)


@override_settings(SECURE_SSL_REDIRECT=False)
class NotasNotificationMetaTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.profesor = _make_user("profe_notas_notif", ["Profesores"])
        self.padre = _make_user("padre_notas_notif", ["Padres"])
        self.school = School.objects.create(name="Colegio Notas Meta", slug="colegio-notas-meta")
        self.course = SchoolCourse.objects.create(school=self.school, code="1A", name="1A Norte", sort_order=1)
        self.alumno = Alumno.objects.create(
            school=self.school,
            nombre="Luna",
            apellido="Meta",
            id_alumno="LEGMETA01",
            curso="1A",
            padre=self.padre,
        )
        ProfesorCurso.objects.create(school=self.school, profesor=self.profesor, curso="1A")
        self.client.force_authenticate(user=self.profesor)

    def test_crear_nota_api_incluye_school_course_en_notificacion(self):
        res = self.client.post(
            "/api/calificaciones/notas/",
            {
                "alumno": self.alumno.id,
                "materia": "Lengua",
                "tipo": "Examen",
                "resultado": "TEA",
                "calificacion": "TEA",
                "cuatrimestre": 1,
                "fecha": "2026-03-12",
            },
            format="json",
            HTTP_X_SCHOOL=self.school.slug,
        )

        self.assertEqual(res.status_code, 201)
        notif = Notificacion.objects.filter(tipo="nota", destinatario=self.padre).latest("id")
        self.assertEqual(notif.meta["school_course_id"], self.course.id)
        self.assertEqual(notif.meta["school_course_name"], "1A Norte")
        self.assertNotIn("curso", notif.meta)
        self.assertIn("1A Norte", notif.descripcion)

    def test_crear_notas_masivo_incluye_school_course_en_notificacion(self):
        res = self.client.post(
            "/api/calificaciones/notas/masivo/",
            {
                "notas": [
                    {
                        "alumno": self.alumno.id,
                        "materia": "Lengua",
                        "tipo": "Examen",
                        "resultado": "TEA",
                        "calificacion": "TEA",
                        "cuatrimestre": 1,
                        "fecha": "2026-03-12",
                    },
                    {
                        "alumno": self.alumno.id,
                        "materia": "Matemática",
                        "tipo": "Trabajo Práctico",
                        "resultado": "TEP",
                        "calificacion": "TEP",
                        "cuatrimestre": 1,
                        "fecha": "2026-03-13",
                    },
                ]
            },
            format="json",
            HTTP_X_SCHOOL=self.school.slug,
        )

        self.assertEqual(res.status_code, 201)
        notif = Notificacion.objects.filter(tipo="nota", destinatario=self.padre).latest("id")
        self.assertEqual(notif.meta["school_course_id"], self.course.id)
        self.assertEqual(notif.meta["school_course_name"], "1A Norte")
        self.assertNotIn("curso", notif.meta)
        self.assertIn("1A Norte", notif.descripcion)
