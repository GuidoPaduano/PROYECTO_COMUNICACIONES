from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from calificaciones.models import Alumno, School, SchoolCourse
from calificaciones.models_preceptores import PreceptorCurso, ProfesorCurso, SchoolAdmin


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
        self.school_admin_group, _ = Group.objects.get_or_create(name="Administradores")

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

    def test_post_crea_profesor_con_asignaciones_iniciales(self):
        response = self.client.post(
            "/api/admin/users/create/",
            {
                "first_name": "Luz",
                "last_name": "Docente",
                "username": "luz_docente",
                "email": "luz@example.com",
                "password": "ClaveSegura123!",
                "password_confirm": "ClaveSegura123!",
                "role": "Profesores",
                "school_course_ids": [self.course_a.id, self.course_b.id],
            },
            format="json",
            HTTP_X_SCHOOL=self.school.slug,
        )
        self.assertEqual(response.status_code, 201)

        docente = get_user_model().objects.get(username="luz_docente")
        self.assertTrue(docente.groups.filter(name="Profesores").exists())
        self.assertEqual(
            list(
                ProfesorCurso.objects.filter(profesor=docente, school=self.school)
                .order_by("school_course__sort_order")
                .values_list("school_course_id", flat=True)
            ),
            [self.course_a.id, self.course_b.id],
        )

    def test_post_crea_alumno_y_lo_vincula_a_legajo_existente(self):
        alumno = Alumno.objects.create(
            school=self.school,
            school_course=self.course_a,
            curso=self.course_a.code,
            nombre="Eva",
            apellido="Suarez",
            id_alumno="LEG100",
        )

        response = self.client.post(
            "/api/admin/users/create/",
            {
                "first_name": "Eva",
                "last_name": "Suarez",
                "username": "LEG100",
                "email": "",
                "password": "ClaveSegura123!",
                "password_confirm": "ClaveSegura123!",
                "role": "Alumnos",
                "alumno_id": alumno.id,
            },
            format="json",
            HTTP_X_SCHOOL=self.school.slug,
        )
        self.assertEqual(response.status_code, 201)

        alumno.refresh_from_db()
        self.assertIsNotNone(alumno.usuario_id)
        self.assertEqual(alumno.usuario.username, "LEG100")

    def test_post_crea_admin_de_colegio_y_asigna_schooladmin(self):
        response = self.client.post(
            "/api/admin/users/create/",
            {
                "first_name": "Ada",
                "last_name": "Admin",
                "username": "ada_admin",
                "email": "ada@example.com",
                "password": "ClaveSegura123!",
                "password_confirm": "ClaveSegura123!",
                "role": "Administradores",
            },
            format="json",
            HTTP_X_SCHOOL=self.school.slug,
        )
        self.assertEqual(response.status_code, 201)

        usuario = get_user_model().objects.get(username="ada_admin")
        self.assertTrue(usuario.groups.filter(name="Administradores").exists())
        self.assertTrue(SchoolAdmin.objects.filter(school=self.school, admin=usuario).exists())

    def test_post_permite_crear_usuario_con_contrasena_corta(self):
        response = self.client.post(
            "/api/admin/users/create/",
            {
                "first_name": "Ana",
                "last_name": "Corta",
                "username": "ana_corta",
                "email": "ana.corta@example.com",
                "password": "1",
                "password_confirm": "1",
                "role": "Administradores",
            },
            format="json",
            HTTP_X_SCHOOL=self.school.slug,
        )
        self.assertEqual(response.status_code, 201)

        usuario = get_user_model().objects.get(username="ana_corta")
        self.assertTrue(usuario.check_password("1"))
        self.assertTrue(usuario.groups.filter(name="Administradores").exists())
        self.assertTrue(SchoolAdmin.objects.filter(school=self.school, admin=usuario).exists())

    def test_post_rechaza_usuario_sin_nombre(self):
        response = self.client.post(
            "/api/admin/users/create/",
            {
                "first_name": "   ",
                "last_name": "Apellido",
                "username": "sin_nombre",
                "email": "sin.nombre@example.com",
                "password": "1",
                "password_confirm": "1",
                "role": "Administradores",
            },
            format="json",
            HTTP_X_SCHOOL=self.school.slug,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "El nombre es obligatorio.")

    def test_post_rechaza_usuario_sin_apellido(self):
        response = self.client.post(
            "/api/admin/users/create/",
            {
                "first_name": "Nombre",
                "last_name": "   ",
                "username": "sin_apellido",
                "email": "sin.apellido@example.com",
                "password": "1",
                "password_confirm": "1",
                "role": "Administradores",
            },
            format="json",
            HTTP_X_SCHOOL=self.school.slug,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "El apellido es obligatorio.")

    def test_post_rechaza_usuario_con_numero_en_nombre(self):
        response = self.client.post(
            "/api/admin/users/create/",
            {
                "first_name": "N0mbre",
                "last_name": "Apellido",
                "username": "nombre_invalido",
                "email": "nombre.invalido@example.com",
                "password": "1",
                "password_confirm": "1",
                "role": "Administradores",
            },
            format="json",
            HTTP_X_SCHOOL=self.school.slug,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "El nombre no puede contener números.")

    def test_post_rechaza_usuario_con_numero_en_apellido(self):
        response = self.client.post(
            "/api/admin/users/create/",
            {
                "first_name": "Nombre",
                "last_name": "Apell1do",
                "username": "apellido_invalido",
                "email": "apellido.invalido@example.com",
                "password": "1",
                "password_confirm": "1",
                "role": "Administradores",
            },
            format="json",
            HTTP_X_SCHOOL=self.school.slug,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "El apellido no puede contener números.")

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

    def test_directivo_sin_rol_admin_de_colegio_no_puede_usar_admin_staff(self):
        directivo = _make_user("directivo_sin_admin")
        directivo.groups.add(self.dir_group)
        self.client.force_authenticate(user=directivo)

        response = self.client.get("/api/admin/staff/", HTTP_X_SCHOOL=self.school.slug)
        self.assertEqual(response.status_code, 403)

    def test_admin_de_colegio_puede_usar_admin_staff_en_su_colegio(self):
        school_admin = _make_user("admin_colegio")
        school_admin.groups.add(self.school_admin_group)
        SchoolAdmin.objects.create(school=self.school, admin=school_admin)
        self.client.force_authenticate(user=school_admin)

        response = self.client.get("/api/admin/staff/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["school"]["slug"], self.school.slug)

    def test_school_user_directory_separa_profesores_preceptores_y_alumnos_por_curso(self):
        school_admin = _make_user("admin_directorio")
        school_admin.groups.add(self.school_admin_group)
        SchoolAdmin.objects.create(school=self.school, admin=school_admin)
        self.client.force_authenticate(user=school_admin)

        profesor = _make_user("profe_directorio")
        profesor.first_name = "Paula"
        profesor.last_name = "Perez"
        profesor.save(update_fields=["first_name", "last_name"])
        profesor.groups.add(self.prof_group)
        ProfesorCurso.objects.create(
            school=self.school,
            school_course=self.course_a,
            profesor=profesor,
            curso=self.course_a.code,
        )

        preceptor = _make_user("prece_directorio")
        preceptor.groups.add(self.prec_group)
        PreceptorCurso.objects.create(
            school=self.school,
            school_course=self.course_b,
            preceptor=preceptor,
            curso=self.course_b.code,
        )

        alumno_user = _make_user("leg001_user")
        alumno_a = Alumno.objects.create(
            school=self.school,
            school_course=self.course_a,
            curso=self.course_a.code,
            nombre="Lara",
            apellido="Lopez",
            id_alumno="LEG001",
            usuario=alumno_user,
        )
        Alumno.objects.create(
            school=self.school,
            school_course=self.course_b,
            curso=self.course_b.code,
            nombre="Nico",
            apellido="Diaz",
            id_alumno="LEG002",
        )
        Alumno.objects.create(
            school=self.other_school,
            school_course=self.other_course,
            curso=self.other_course.code,
            nombre="Fuera",
            apellido="Scope",
            id_alumno="LEG999",
        )

        response = self.client.get("/api/admin/school-users/", HTTP_X_SCHOOL=self.school.slug)
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertEqual(body["totals"]["profesores"], 1)
        self.assertEqual(body["totals"]["preceptores"], 1)
        self.assertEqual(body["totals"]["alumnos"], 2)
        self.assertEqual([item["username"] for item in body["profesores"]], ["profe_directorio"])
        self.assertEqual([item["username"] for item in body["preceptores"]], ["prece_directorio"])

        grouped = {item["course"]["id"]: item["students"] for item in body["alumnos_por_curso"]}
        self.assertEqual(len(grouped[self.course_a.id]), 1)
        self.assertEqual(grouped[self.course_a.id][0]["id_alumno"], alumno_a.id_alumno)
        self.assertTrue(grouped[self.course_a.id][0]["has_linked_user"])
        self.assertEqual(grouped[self.course_a.id][0]["linked_user"]["username"], "leg001_user")
        self.assertEqual(len(grouped[self.course_b.id]), 1)
        self.assertEqual(grouped[self.course_b.id][0]["id_alumno"], "LEG002")

    def test_school_user_directory_exige_admin_del_colegio_activo(self):
        school_admin = _make_user("admin_otro_colegio")
        school_admin.groups.add(self.school_admin_group)
        SchoolAdmin.objects.create(school=self.other_school, admin=school_admin)
        self.client.force_authenticate(user=school_admin)

        response = self.client.get("/api/admin/school-users/", HTTP_X_SCHOOL=self.school.slug)
        self.assertEqual(response.status_code, 403)
