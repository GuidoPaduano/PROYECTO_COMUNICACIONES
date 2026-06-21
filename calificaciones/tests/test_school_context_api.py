import tempfile
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from unittest.mock import patch

from calificaciones.api_schools import _run_school_deletion_job
from calificaciones.models import Alumno, Mensaje, School, SchoolCourse, SchoolDeletionJob
from calificaciones.models_preceptores import PreceptorCurso, SchoolAdmin, SchoolMembership


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
        self.assertEqual(body["alumno"]["apellido"], "Suarez")
        self.assertNotIn("curso", body["alumno"])

    def test_login_rechaza_usuario_de_otro_colegio(self):
        res = self.client.post(
            "/api/token/",
            {
                "username": self.alumno_user.username,
                "password": "test1234",
                "school": self.school_a.slug,
            },
            format="json",
        )

        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["detail"], "El usuario no pertenece al colegio seleccionado.")
        self.assertEqual(res.cookies["access_token"].value, "")
        self.assertEqual(res.cookies["refresh_token"].value, "")

    def test_login_permite_usuario_en_su_colegio(self):
        res = self.client.post(
            "/api/token/",
            {
                "username": self.alumno_user.username,
                "password": "test1234",
                "school": self.school_b.slug,
            },
            format="json",
        )

        self.assertEqual(res.status_code, 200)
        self.assertIn("access_token", res.cookies)
        self.assertIn("refresh_token", res.cookies)

    def test_directivo_puede_iniciar_sesion_y_cambiar_entre_sus_colegios(self):
        directivo = _make_user("directivo_multi_school")
        directivos_group, _ = Group.objects.get_or_create(name="Directivos")
        directivo.groups.add(directivos_group)
        SchoolMembership.objects.create(school=self.school_a, user=directivo)
        SchoolMembership.objects.create(school=self.school_b, user=directivo)

        login_a = self.client.post(
            "/api/token/",
            {
                "username": directivo.username,
                "password": "test1234",
                "school": self.school_a.slug,
            },
            format="json",
        )
        self.assertEqual(login_a.status_code, 200)

        self.client.force_authenticate(user=directivo)
        whoami_b = self.client.get("/api/auth/whoami/", HTTP_X_SCHOOL=self.school_b.slug)

        self.assertEqual(whoami_b.status_code, 200)
        body = whoami_b.json()
        self.assertEqual(body["school"]["id"], self.school_b.id)
        self.assertEqual(
            {item["id"] for item in body["available_schools"]},
            {self.school_a.id, self.school_b.id},
        )

    def test_directivo_no_puede_usar_un_colegio_sin_membresia(self):
        directivo = _make_user("directivo_school_restringido")
        directivos_group, _ = Group.objects.get_or_create(name="Directivos")
        directivo.groups.add(directivos_group)
        SchoolMembership.objects.create(school=self.school_a, user=directivo)
        school_c = School.objects.create(name="Colegio Contexto Oeste", slug="colegio-contexto-oeste")

        login = self.client.post(
            "/api/token/",
            {
                "username": directivo.username,
                "password": "test1234",
                "school": school_c.slug,
            },
            format="json",
        )

        self.assertEqual(login.status_code, 401)
        self.assertEqual(login.json()["detail"], "El usuario no pertenece al colegio seleccionado.")

    def test_login_regular_sin_colegio_explicito_falla_en_entorno_multicolegios(self):
        res = self.client.post(
            "/api/token/",
            {
                "username": self.alumno_user.username,
                "password": "test1234",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["detail"], "Seleccioná un colegio antes de iniciar sesión.")
        self.assertEqual(res.cookies["access_token"].value, "")
        self.assertEqual(res.cookies["refresh_token"].value, "")

    def test_login_superuser_sin_colegio_explicito_sigue_permitido(self):
        res = self.client.post(
            "/api/token/",
            {
                "username": self.superuser.username,
                "password": "test1234",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 200)
        self.assertIn("access_token", res.cookies)
        self.assertIn("refresh_token", res.cookies)

    def test_whoami_rechaza_header_de_otro_colegio_para_usuario_regular(self):
        self.client.force_authenticate(user=self.alumno_user)

        res = self.client.get("/api/auth/whoami/", HTTP_X_SCHOOL=self.school_a.slug)

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "El usuario no pertenece al colegio seleccionado.")

    def test_cookie_session_no_expone_alumno_de_otro_colegio_con_header_manipulado(self):
        login = self.client.post(
            "/api/token/",
            {
                "username": self.alumno_user.username,
                "password": "test1234",
                "school": self.school_b.slug,
            },
            format="json",
        )
        self.assertEqual(login.status_code, 200)

        foreign_detail = self.client.get(
            "/api/alumnos/CTXPAD001",
            HTTP_X_SCHOOL=self.school_a.slug,
        )
        own_detail = self.client.get(
            "/api/alumnos/CTX001",
            HTTP_X_SCHOOL=self.school_a.slug,
        )

        self.assertIn(foreign_detail.status_code, {403, 404})
        self.assertNotContains(foreign_detail, "Mia", status_code=foreign_detail.status_code)
        self.assertEqual(own_detail.status_code, 200)
        self.assertEqual(own_detail.json()["id_alumno"], "CTX001")
        self.assertNotEqual(own_detail.json().get("school_id"), self.school_a.id)

    def test_usuario_sin_colegio_no_vincula_legajo_de_otro_colegio_con_contexto_manipulado(self):
        unlinked_user = _make_user("alumno_unlinked_school_context")
        alumnos_group = Group.objects.get(name="Alumnos")
        unlinked_user.groups.add(alumnos_group)
        foreign_student = Alumno.objects.get(school=self.school_a, id_alumno="CTXPAD001")

        self.client.force_authenticate(user=unlinked_user)
        response = self.client.post(
            "/api/alumnos/vincular/",
            {"id_alumno": foreign_student.id_alumno},
            format="json",
            HTTP_X_SCHOOL=self.school_a.slug,
        )

        self.assertEqual(response.status_code, 403)
        foreign_student.refresh_from_db()
        self.assertIsNone(foreign_student.usuario_id)

    def test_padre_no_puede_vincularse_como_alumno_en_su_colegio(self):
        unlinked_student = Alumno.objects.create(
            school=self.school_a,
            school_course=self.course_a,
            nombre="Noa",
            apellido="Sin vincular",
            id_alumno="CTXPAD002",
            curso="1A",
        )
        self.client.force_authenticate(user=self.padre_user)

        response = self.client.post(
            "/api/alumnos/vincular/",
            {"id_alumno": unlinked_student.id_alumno},
            format="json",
            HTTP_X_SCHOOL=self.school_a.slug,
        )

        self.assertEqual(response.status_code, 403)
        unlinked_student.refresh_from_db()
        self.assertIsNone(unlinked_student.usuario_id)

    def test_admin_colegio_no_transfiere_alumno_o_curso_de_otro_colegio_por_id(self):
        admin_user = _make_user("admin_boundary_school_context")
        admin_group, _ = Group.objects.get_or_create(name="Administradores")
        admin_user.groups.add(admin_group)
        SchoolAdmin.objects.create(school=self.school_a, admin=admin_user)
        local_student = Alumno.objects.get(school=self.school_a, id_alumno="CTXPAD001")
        foreign_student = Alumno.objects.get(school=self.school_b, id_alumno="CTX001")
        original_local_course = local_student.school_course_id
        original_foreign_course = foreign_student.school_course_id
        self.client.force_authenticate(user=admin_user)

        foreign_student_response = self.client.post(
            "/api/alumnos/transferir/",
            {
                "alumno_id": foreign_student.id,
                "school_course_id": self.course_a.id,
            },
            format="json",
            HTTP_X_SCHOOL=self.school_a.slug,
        )
        foreign_course_response = self.client.post(
            "/api/alumnos/transferir/",
            {
                "alumno_id": local_student.id,
                "school_course_id": self.course_b.id,
            },
            format="json",
            HTTP_X_SCHOOL=self.school_a.slug,
        )

        self.assertEqual(foreign_student_response.status_code, 404)
        self.assertEqual(foreign_course_response.status_code, 400)
        local_student.refresh_from_db()
        foreign_student.refresh_from_db()
        self.assertEqual(local_student.school_course_id, original_local_course)
        self.assertEqual(foreign_student.school_course_id, original_foreign_course)

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

    def test_superuser_no_puede_crear_colegio_con_nombre_duplicado_sin_importar_mayusculas(self):
        self.client.force_authenticate(user=self.superuser)

        res = self.client.post(
            "/api/admin/schools/",
            {
                "name": "colegio contexto norte",
                "short_name": "Contexto Norte 2",
                "logo_url": "/imagenes/contexto-norte-2.png",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["errors"]["name"], ["Ya existe un colegio con ese nombre."])

    def test_superuser_no_puede_crear_colegio_con_nombre_corto_duplicado_sin_importar_mayusculas(self):
        self.client.force_authenticate(user=self.superuser)

        res = self.client.post(
            "/api/admin/schools/",
            {
                "name": "Colegio Contexto Oeste",
                "short_name": "contexto norte",
                "logo_url": "/imagenes/contexto-oeste.png",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["errors"]["short_name"], ["Ya existe un colegio con ese nombre corto."])

    def test_superuser_no_puede_renombrar_colegio_con_nombre_existente_sin_importar_mayusculas(self):
        self.client.force_authenticate(user=self.superuser)

        res = self.client.patch(
            f"/api/admin/schools/{self.school_b.id}/",
            {"name": "colegio contexto norte"},
            format="json",
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["errors"]["name"], ["Ya existe un colegio con ese nombre."])

    def test_superuser_puede_subir_logo_de_colegio(self):
        self.client.force_authenticate(user=self.superuser)
        logo = SimpleUploadedFile(
            "nuevo-logo.png",
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
            content_type="image/png",
        )

        with tempfile.TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            res = self.client.post(
                f"/api/admin/schools/{self.school_a.id}/logo/",
                {"logo": logo},
                format="multipart",
            )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["logo_url"].startswith("/media/school-logos/"))
        self.school_a.refresh_from_db()
        self.assertEqual(self.school_a.logo_url, body["logo_url"])
        self.assertEqual(body["school"]["logo_url"], body["logo_url"])

    def test_usuario_regular_no_puede_crear_colegio(self):
        self.client.force_authenticate(user=self.alumno_user)

        res = self.client.post(
            "/api/admin/schools/",
            {"name": "Colegio Bloqueado"},
            format="json",
        )

        self.assertEqual(res.status_code, 403)
        self.assertFalse(School.objects.filter(name="Colegio Bloqueado").exists())

    def test_superuser_puede_borrar_colegio_sin_dependencias(self):
        self.client.force_authenticate(user=self.superuser)
        school = School.objects.create(
            name="Colegio Borrable",
            short_name="Borrable",
            slug="colegio-borrable",
            logo_url="",
            primary_color="#112233",
            accent_color="#445566",
        )

        with patch("calificaciones.api_schools._schedule_school_deletion_job") as mocked_schedule:
            with self.captureOnCommitCallbacks(execute=True):
                res = self.client.delete(f"/api/admin/schools/{school.id}/")

        self.assertEqual(res.status_code, 202)
        mocked_schedule.assert_called_once()
        job = SchoolDeletionJob.objects.get(pk=res.json()["job"]["id"])
        self.assertEqual(job.status, SchoolDeletionJob.STATUS_PENDING)
        _run_school_deletion_job(job.id)
        self.assertFalse(School.objects.filter(pk=school.id).exists())
        self.assertEqual(res.json()["deleted_id"], school.id)

        status_res = self.client.get(f"/api/admin/school-deletion-jobs/{job.id}/")
        self.assertEqual(status_res.status_code, 200)
        self.assertEqual(status_res.json()["job"]["status"], SchoolDeletionJob.STATUS_COMPLETED)
        self.assertIsNotNone(status_res.json()["job"]["finished_at"])

    def test_usuario_regular_no_puede_consultar_job_de_borrado(self):
        job = SchoolDeletionJob.objects.create(
            school=self.school_a,
            requested_by=self.superuser,
            school_name=self.school_a.name,
            school_slug=self.school_a.slug,
        )
        self.client.force_authenticate(user=self.alumno_user)

        res = self.client.get(f"/api/admin/school-deletion-jobs/{job.id}/")

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No autorizado.")

    def test_superuser_no_puede_borrar_colegio_con_dependencias(self):
        self.client.force_authenticate(user=self.superuser)
        preceptor = _make_user("preceptor_delete_school_context")
        admin_user = _make_user("admin_delete_school_context")
        SchoolAdmin.objects.create(school=self.school_a, admin=admin_user)
        PreceptorCurso.objects.create(
            school=self.school_a,
            preceptor=preceptor,
            curso="1A",
        )
        Mensaje.objects.create(
            school=self.school_a,
            school_course=self.course_a,
            remitente=self.superuser,
            destinatario=preceptor,
            curso="1A",
            asunto="Prueba",
            contenido="Mensaje asociado al colegio",
        )

        with patch("calificaciones.api_schools._schedule_school_deletion_job") as mocked_schedule:
            with self.captureOnCommitCallbacks(execute=True):
                res = self.client.delete(f"/api/admin/schools/{self.school_a.id}/")

        self.assertEqual(res.status_code, 202)
        mocked_schedule.assert_called_once()
        job = SchoolDeletionJob.objects.get(pk=res.json()["job"]["id"])
        self.assertEqual(job.status, SchoolDeletionJob.STATUS_PENDING)
        self.school_a.refresh_from_db()
        self.assertFalse(self.school_a.is_active)

        _run_school_deletion_job(job.id)

        self.assertFalse(School.objects.filter(pk=self.school_a.id).exists())
        self.assertFalse(SchoolCourse.objects.filter(pk=self.course_a.id).exists())
        self.assertFalse(Alumno.objects.filter(school=self.school_a).exists())
        self.assertFalse(PreceptorCurso.objects.filter(school=self.school_a).exists())
        self.assertFalse(SchoolAdmin.objects.filter(school=self.school_a).exists())
        self.assertFalse(Mensaje.objects.filter(school=self.school_a).exists())
        self.assertTrue(School.objects.filter(pk=self.school_b.id).exists())
        self.assertEqual(res.json()["deleted_id"], self.school_a.id)
        self.assertEqual(res.json()["detail"], "Borrado iniciado.")

    def test_superuser_admin_school_courses_respeta_colegio_solicitado(self):
        self.client.force_authenticate(user=self.superuser)

        res = self.client.get("/api/admin/school-courses/", {"school": self.school_b.slug})

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(len(body["schools"]), 1)
        self.assertEqual(body["schools"][0]["id"], self.school_b.id)
        self.assertEqual(body["schools"][0]["name"], self.school_b.name)
        self.assertEqual(body["schools"][0]["courses"][0]["name"], "1A Sur")
        self.assertEqual(body["schools"][0]["courses"][0]["students_count"], 1)
