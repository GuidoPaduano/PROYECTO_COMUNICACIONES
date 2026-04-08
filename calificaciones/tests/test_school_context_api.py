from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from calificaciones.models import Alumno, School, SchoolCourse
from calificaciones.models_preceptores import PreceptorCurso


def _make_user(username: str, *, is_superuser: bool = False):
    User = get_user_model()
    return User.objects.create_user(
        username=username,
        password="test1234",
        is_superuser=is_superuser,
        is_staff=is_superuser,
    )


@override_settings(SECURE_SSL_REDIRECT=False)
class SchoolContextApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.superuser = _make_user("admin_school_context", is_superuser=True)
        self.alumno_user = _make_user("alumno_school_context")
        self.padre_user = _make_user("padre_school_context")
        alumnos_group, _ = Group.objects.get_or_create(name="Alumnos")
        padres_group, _ = Group.objects.get_or_create(name="Padres")
        self.alumno_user.groups.add(alumnos_group)
        self.padre_user.groups.add(padres_group)
        self.school_a = School.objects.create(
            name="Colegio Contexto Norte",
            short_name="Contexto Norte",
            slug="colegio-contexto-norte",
            logo_url="/imagenes/Logo%20Color.png",
            primary_color="#123456",
            accent_color="#abcdef",
        )
        self.school_b = School.objects.create(
            name="Colegio Contexto Sur",
            short_name="Contexto Sur",
            slug="colegio-contexto-sur",
            logo_url="/imagenes/tecnova(1).png",
            primary_color="#654321",
            accent_color="#fedcba",
        )
        self.course_a = SchoolCourse.objects.create(school=self.school_a, code="1A", name="1A Norte", sort_order=1)
        self.course_b = SchoolCourse.objects.create(school=self.school_b, code="1A", name="1A Sur", sort_order=1)
        Alumno.objects.create(
            school=self.school_a,
            nombre="Mia",
            apellido="Padre",
            id_alumno="CTXPAD001",
            curso="1A",
            padre=self.padre_user,
        )
        Alumno.objects.create(
            school=self.school_b,
            nombre="Lara",
            apellido="Suarez",
            id_alumno="CTX001",
            curso="1A",
            usuario=self.alumno_user,
        )

    def test_superuser_whoami_incluye_available_schools_y_respeta_query(self):
        self.client.force_authenticate(user=self.superuser)

        res = self.client.get("/api/auth/whoami/", {"school": self.school_b.slug})

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertNotIn("is_staff", body)
        self.assertNotIn("hijos", body)
        self.assertNotIn("grupos", body)
        self.assertEqual(body["school"]["id"], self.school_b.id)
        self.assertEqual(body["school"]["short_name"], "Contexto Sur")
        self.assertEqual(body["school"]["logo_url"], "/imagenes/tecnova(1).png")
        self.assertEqual(body["school"]["primary_color"], "#654321")
        self.assertEqual(body["school"]["accent_color"], "#fedcba")
        available_ids = {item["id"] for item in body["available_schools"]}
        self.assertIn(self.school_a.id, available_ids)
        self.assertIn(self.school_b.id, available_ids)

    def test_superuser_perfil_api_respeta_header_de_school(self):
        self.client.force_authenticate(user=self.superuser)

        res = self.client.get("/api/perfil_api/", HTTP_X_SCHOOL=self.school_a.slug)

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertNotIn("alumno_resolution", body)
        self.assertNotIn("grupos", body)
        self.assertEqual(body["school"]["id"], self.school_a.id)
        self.assertEqual(body["school"]["short_name"], "Contexto Norte")
        available_ids = {item["id"] for item in body["available_schools"]}
        self.assertIn(self.school_a.id, available_ids)
        self.assertIn(self.school_b.id, available_ids)

    def test_superuser_whoami_sin_school_explicito_no_fuerza_default(self):
        self.client.force_authenticate(user=self.superuser)

        res = self.client.get("/api/auth/whoami/")

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIsNone(body["school"])
        available_ids = {item["id"] for item in body["available_schools"]}
        self.assertIn(self.school_a.id, available_ids)
        self.assertIn(self.school_b.id, available_ids)

    def test_preceptor_perfil_api_expone_cursos_asignados_reales(self):
        preceptor = _make_user("preceptor_school_context")
        preceptores_group, _ = Group.objects.get_or_create(name="Preceptores")
        preceptor.groups.add(preceptores_group)
        PreceptorCurso.objects.create(
            school=self.school_a,
            preceptor=preceptor,
            curso="1A",
        )
        self.client.force_authenticate(user=preceptor)

        res = self.client.get("/api/perfil_api/", {"school": self.school_a.slug})

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["assigned_school_courses"][0]["school_course_id"], self.course_a.id)
        self.assertEqual(body["assigned_school_courses"][0]["code"], "1A")
        self.assertEqual(body["assigned_school_courses"][0]["nombre"], "1A Norte")
        self.assertNotIn("curso_preceptor", body)
        self.assertNotIn("grupos", body)

    def test_padre_perfil_api_expone_children_y_no_alias_legacy(self):
        self.client.force_authenticate(user=self.padre_user)

        res = self.client.get("/api/perfil_api/", {"school": self.school_a.slug})

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertNotIn("alumnos_del_padre", body)
        self.assertNotIn("grupos", body["user"])
        self.assertEqual([item["id_alumno"] for item in body["children"]], ["CTXPAD001"])
        self.assertEqual(body["children"][0]["school_course_name"], "1A Norte")

    def test_usuario_regular_recibe_solo_su_school_disponible(self):
        self.client.force_authenticate(user=self.alumno_user)

        res = self.client.get("/api/auth/whoami/")

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertNotIn("is_staff", body)
        self.assertNotIn("alumno_resolution", body)
        self.assertNotIn("hijos", body)
        self.assertNotIn("grupos", body)
        self.assertEqual(body["school"]["id"], self.school_b.id)
        self.assertEqual(body["available_schools"][0]["id"], self.school_b.id)
        self.assertEqual(body["available_schools"][0]["short_name"], "Contexto Sur")
        self.assertEqual(body["available_schools"][0]["logo_url"], "/imagenes/tecnova(1).png")
        self.assertEqual(body["available_schools"][0]["primary_color"], "#654321")
        self.assertEqual(body["available_schools"][0]["accent_color"], "#fedcba")
        self.assertEqual(body["alumno"]["school_course_name"], "1A Sur")
        self.assertNotIn("curso", body["alumno"])

    def test_mi_perfil_no_expone_alias_legacy_de_alumno(self):
        self.client.force_login(self.alumno_user)

        res = self.client.get("/api/mi-perfil/")

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertNotIn("alumno_id", body)
        self.assertNotIn("id_alumno", body)
        self.assertEqual(body["alumno"]["id_alumno"], "CTX001")
        self.assertEqual(body["alumno"]["school_course_name"], "1A Sur")

    def test_public_school_branding_devuelve_contexto_visual(self):
        res = self.client.get("/api/public/school-branding/", {"school": self.school_a.slug})

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["school"]["id"], self.school_a.id)
        self.assertEqual(body["school"]["short_name"], "Contexto Norte")
        self.assertEqual(body["school"]["logo_url"], "/imagenes/Logo%20Color.png")
        self.assertEqual(body["school"]["primary_color"], "#123456")
        self.assertEqual(body["school"]["accent_color"], "#abcdef")

    def test_public_school_branding_sin_school_no_fuerza_default(self):
        res = self.client.get("/api/public/school-branding/")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"school": None})

    @override_settings(SCHOOL_PARENT_HOSTS=["alumnix.com"], ALLOWED_HOSTS=["testserver", ".alumnix.com"])
    def test_public_school_branding_resuelve_colegio_desde_subdominio(self):
        res = self.client.get(
            "/api/public/school-branding/",
            HTTP_HOST=f"{self.school_b.slug}.alumnix.com",
        )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["school"]["id"], self.school_b.id)
        self.assertEqual(body["school"]["slug"], self.school_b.slug)

    def test_public_school_directory_lista_colegios_activos(self):
        res = self.client.get("/api/public/schools/")

        self.assertEqual(res.status_code, 200)
        body = res.json()
        slugs = [item["slug"] for item in body["schools"]]
        self.assertIn(self.school_a.slug, slugs)
        self.assertIn(self.school_b.slug, slugs)

    def test_superuser_puede_crear_colegio_con_catalogo_base(self):
        self.client.force_authenticate(user=self.superuser)

        res = self.client.post(
            "/api/admin/schools/",
            {
                "name": "Colegio Contexto Centro",
                "short_name": "Contexto Centro",
                "logo_url": "/imagenes/contexto-centro.png",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertEqual(body["school"]["slug"], "colegio-contexto-centro")
        self.assertEqual(body["school"]["primary_color"], "#0C1B3F")
        self.assertEqual(body["school"]["accent_color"], "#1D4ED8")
        self.assertEqual(body["seeded_courses"], 12)

        school = School.objects.get(name="Colegio Contexto Centro")
        self.assertEqual(school.logo_url, "/imagenes/contexto-centro.png")
        self.assertEqual(
            list(
                SchoolCourse.objects.filter(school=school)
                .order_by("sort_order")
                .values_list("code", flat=True)
            ),
            ["1A", "1B", "2A", "2B", "3A", "3B", "4ECO", "4NAT", "5ECO", "5NAT", "6ECO", "6NAT"],
        )
        available_ids = {item["id"] for item in body["available_schools"]}
        self.assertIn(school.id, available_ids)

    def test_usuario_regular_no_puede_crear_colegio(self):
        self.client.force_authenticate(user=self.alumno_user)

        res = self.client.post(
            "/api/admin/schools/",
            {"name": "Colegio Bloqueado"},
            format="json",
        )

        self.assertEqual(res.status_code, 403)
        self.assertFalse(School.objects.filter(name="Colegio Bloqueado").exists())
