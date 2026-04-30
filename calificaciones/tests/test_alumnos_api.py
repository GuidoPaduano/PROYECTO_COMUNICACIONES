from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from calificaciones.api_asistencias import _bulk_upsert_asistencias
from calificaciones.models import Alumno, Asistencia, Nota, School, SchoolCourse
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


def _make_superuser(username: str):
    return _make_user(username, is_superuser=True)


@override_settings(SECURE_SSL_REDIRECT=False)
class CursosDisponiblesSchoolCatalogTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = _make_superuser("admin_alumnos_school")
        self.school_a = School.objects.create(name="Colegio Cursos Norte", slug="colegio-cursos-norte")
        self.school_b = School.objects.create(name="Colegio Cursos Sur", slug="colegio-cursos-sur")
        SchoolCourse.objects.create(school=self.school_a, code="1A", name="Primer A Norte", sort_order=1)
        SchoolCourse.objects.create(school=self.school_a, code="2A", name="Segundo A Norte", sort_order=2)
        SchoolCourse.objects.create(school=self.school_b, code="1A", name="Primer A Sur", sort_order=1)
        self.client.force_authenticate(user=self.admin)

    def test_cursos_disponibles_usa_catalogo_del_school_activo(self):
        res = self.client.get(
            "/api/alumnos/cursos/",
            {"school": self.school_a.slug},
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            res.json()["cursos"],
            [
                {"id": "1A", "nombre": "Primer A Norte"},
                {"id": "2A", "nombre": "Segundo A Norte"},
            ],
        )


@override_settings(SECURE_SSL_REDIRECT=False)
class AlumnoSchoolCourseSyncTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = _make_superuser("admin_alumnos_sync")
        self.preceptor = _make_user("preceptor_alumnos_sync", ["Preceptores"])
        self.directivo = _make_user("directivo_alumnos_sync", ["Directivos"])
        self.profesor = _make_user("profesor_alumnos_sync", ["Profesores"])
        self.default_school = School.objects.get(slug="escuela-tecnova")
        self.default_curso_2a, _ = SchoolCourse.objects.get_or_create(
            school=self.default_school,
            code="2A",
            defaults={"name": "Segundo A Default", "sort_order": 2},
        )
        self.school = School.objects.create(name="Colegio Sync", slug="colegio-sync")
        self.curso_1a = SchoolCourse.objects.create(
            school=self.school,
            code="1A",
            name="Primero A",
            sort_order=1,
        )
        self.curso_2a = SchoolCourse.objects.create(
            school=self.school,
            code="2A",
            name="Segundo A",
            sort_order=2,
        )

    def test_crear_alumno_asigna_school_course_del_catalogo_activo(self):
        self.client.force_authenticate(user=self.admin)

        res = self.client.post(
            "/api/alumnos/crear/",
            {
                "id_alumno": "LEG100",
                "nombre": "Luca",
                "apellido": "Perez",
                "school_course_id": self.curso_1a.id,
            },
            format="json",
            HTTP_X_SCHOOL=self.school.slug,
        )

        self.assertEqual(res.status_code, 201)
        self.assertNotIn("ok", res.json())
        body = res.json()["alumno"]
        alumno = Alumno.objects.get(pk=body["id"])
        self.assertNotIn("curso", body)
        self.assertEqual(alumno.school_id, self.school.id)
        self.assertEqual(alumno.school_course_id, self.curso_1a.id)
        self.assertEqual(body["school_course_id"], self.curso_1a.id)

    def test_crear_alumno_rechaza_curso_legacy(self):
        self.client.force_authenticate(user=self.admin)

        res = self.client.post(
            "/api/alumnos/crear/",
            {
                "id_alumno": "LEG100A",
                "nombre": "Luca Legacy",
                "apellido": "Perez",
                "curso": "1A",
            },
            format="json",
            HTTP_X_SCHOOL=self.school.slug,
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            res.json()["detail"],
            "El parámetro 'curso' está deprecado en este endpoint. Usa school_course_id.",
        )

    def test_crear_alumno_acepta_school_course_id_sin_curso(self):
        self.client.force_authenticate(user=self.admin)

        res = self.client.post(
            "/api/alumnos/crear/",
            {
                "id_alumno": "LEG101",
                "nombre": "Mora",
                "apellido": "Diaz",
                "school_course_id": self.curso_2a.id,
            },
            format="json",
            HTTP_X_SCHOOL=self.school.slug,
        )

        self.assertEqual(res.status_code, 201)
        body = res.json()["alumno"]
        self.assertNotIn("curso", body)
        alumno = Alumno.objects.get(pk=body["id"])
        self.assertEqual(alumno.curso, "2A")
        self.assertEqual(alumno.school_course_id, self.curso_2a.id)

    def test_crear_alumno_preceptor_requiere_asignacion_al_curso_destino(self):
        PreceptorCurso.objects.create(
            school=self.school,
            preceptor=self.preceptor,
            curso="1A",
        )
        self.client.force_authenticate(user=self.preceptor)

        res = self.client.post(
            "/api/alumnos/crear/",
            {
                "id_alumno": "LEG102",
                "nombre": "Nora",
                "apellido": "Lopez",
                "school_course_id": self.curso_2a.id,
            },
            format="json",
            HTTP_X_SCHOOL=self.school.slug,
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No autorizado para crear alumnos en ese curso.")
        self.assertFalse(Alumno.objects.filter(id_alumno="LEG102", school=self.school).exists())

    def test_crear_alumno_directivo_puede_operar_en_cualquier_curso_del_colegio(self):
        self.client.force_authenticate(user=self.directivo)

        res = self.client.post(
            "/api/alumnos/crear/",
            {
                "id_alumno": "LEG103",
                "nombre": "Brisa",
                "apellido": "Diaz",
                "school_course_id": self.default_curso_2a.id,
            },
            format="json",
        )

        self.assertEqual(res.status_code, 201)
        alumno = Alumno.objects.get(pk=res.json()["alumno"]["id"])
        self.assertEqual(alumno.school_id, self.default_school.id)
        self.assertEqual(alumno.school_course_id, self.default_curso_2a.id)

    def test_transferir_alumno_actualiza_school_course_con_update_fields(self):
        alumno = Alumno.objects.create(
            school=self.school,
            nombre="Aina",
            apellido="Lopez",
            id_alumno="LEG200",
            curso="1A",
        )
        PreceptorCurso.objects.create(
            school=self.school,
            preceptor=self.preceptor,
            curso="1A",
        )
        PreceptorCurso.objects.create(
            school=self.school,
            preceptor=self.preceptor,
            curso="2A",
        )
        self.client.force_authenticate(user=self.preceptor)

        res = self.client.post(
            "/api/alumnos/transferir/",
            {
                "alumno_id": alumno.id,
                "school_course_id": self.curso_2a.id,
            },
            format="json",
        )

        self.assertEqual(res.status_code, 200)
        self.assertNotIn("ok", res.json())
        alumno.refresh_from_db()
        self.assertNotIn("curso", res.json()["alumno"])
        self.assertEqual(alumno.curso, "2A")
        self.assertEqual(alumno.school_course_id, self.curso_2a.id)
        self.assertEqual(res.json()["alumno"]["school_course_id"], self.curso_2a.id)

    def test_transferir_alumno_rechaza_curso_legacy(self):
        alumno = Alumno.objects.create(
            school=self.school,
            nombre="Aina Legacy",
            apellido="Lopez",
            id_alumno="LEG200A",
            curso="1A",
        )
        PreceptorCurso.objects.create(
            school=self.school,
            preceptor=self.preceptor,
            curso="1A",
        )
        PreceptorCurso.objects.create(
            school=self.school,
            preceptor=self.preceptor,
            curso="2A",
        )
        self.client.force_authenticate(user=self.preceptor)

        res = self.client.post(
            "/api/alumnos/transferir/",
            {
                "alumno_id": alumno.id,
                "curso": "2A",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            res.json()["detail"],
            "El parámetro 'curso' está deprecado en este endpoint. Usa school_course_id.",
        )

    def test_transferir_alumno_acepta_school_course_id_sin_curso(self):
        alumno = Alumno.objects.create(
            school=self.school,
            nombre="Tina",
            apellido="Rios",
            id_alumno="LEG201",
            curso="1A",
        )
        PreceptorCurso.objects.create(
            school=self.school,
            preceptor=self.preceptor,
            curso="1A",
        )
        PreceptorCurso.objects.create(
            school=self.school,
            preceptor=self.preceptor,
            curso="2A",
        )
        self.client.force_authenticate(user=self.preceptor)

        res = self.client.post(
            "/api/alumnos/transferir/",
            {
                "alumno_id": alumno.id,
                "school_course_id": self.curso_2a.id,
            },
            format="json",
        )

        self.assertEqual(res.status_code, 200)
        alumno.refresh_from_db()
        self.assertNotIn("curso", res.json()["alumno"])
        self.assertEqual(alumno.curso, "2A")
        self.assertEqual(alumno.school_course_id, self.curso_2a.id)

    def test_transferir_alumno_rechaza_curso_destino_sin_asignacion(self):
        alumno = Alumno.objects.create(
            school=self.school,
            nombre="Nina",
            apellido="Rios",
            id_alumno="LEG202",
            curso="1A",
        )
        PreceptorCurso.objects.create(
            school=self.school,
            preceptor=self.preceptor,
            curso="1A",
        )
        self.client.force_authenticate(user=self.preceptor)

        res = self.client.post(
            "/api/alumnos/transferir/",
            {
                "alumno_id": alumno.id,
                "school_course_id": self.curso_2a.id,
            },
            format="json",
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No autorizado para transferir al curso destino.")
        alumno.refresh_from_db()
        self.assertEqual(alumno.curso, "1A")
        self.assertEqual(alumno.school_course_id, self.curso_1a.id)

    def test_transferir_alumno_directivo_no_requiere_asignacion_puntual(self):
        alumno = Alumno.objects.create(
            school=self.default_school,
            nombre="Uma",
            apellido="Farias",
            id_alumno="LEG203",
            curso="1A",
        )
        self.client.force_authenticate(user=self.directivo)

        res = self.client.post(
            "/api/alumnos/transferir/",
            {
                "alumno_id": alumno.id,
                "school_course_id": self.default_curso_2a.id,
            },
            format="json",
        )

        self.assertEqual(res.status_code, 200)
        self.assertNotIn("ok", res.json())
        alumno.refresh_from_db()
        self.assertEqual(alumno.school_course_id, self.default_curso_2a.id)
        self.assertEqual(alumno.curso, "2A")

    def test_asignaciones_docente_y_preceptor_se_enlazan_a_school_course(self):
        asignacion_preceptor = PreceptorCurso.objects.create(
            school=self.school,
            preceptor=self.preceptor,
            curso="1A",
        )
        asignacion_profesor = ProfesorCurso.objects.create(
            school=self.school,
            profesor=self.profesor,
            curso="2A",
        )

        self.assertEqual(asignacion_preceptor.school_course_id, self.curso_1a.id)
        self.assertEqual(asignacion_profesor.school_course_id, self.curso_2a.id)


@override_settings(SECURE_SSL_REDIRECT=False)
class AlumnoLegajoPorSchoolTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = _make_superuser("admin_alumnos_legajos")
        self.school_a = School.objects.create(name="Colegio Legajos Norte", slug="colegio-legajos-norte")
        self.school_b = School.objects.create(name="Colegio Legajos Sur", slug="colegio-legajos-sur")
        self.course_a_1a = SchoolCourse.objects.create(school=self.school_a, code="1A", name="1A Norte", sort_order=1)
        self.course_b_1a = SchoolCourse.objects.create(school=self.school_b, code="1A", name="1A Sur", sort_order=1)
        self.client.force_authenticate(user=self.admin)

    def test_modelo_permita_mismo_legajo_en_distintos_colegios(self):
        alumno_a = Alumno.objects.create(
            school=self.school_a,
            nombre="Luca",
            apellido="Perez",
            id_alumno="LEG500",
            curso="1A",
        )
        alumno_b = Alumno.objects.create(
            school=self.school_b,
            nombre="Mora",
            apellido="Diaz",
            id_alumno="LEG500",
            curso="1A",
        )

        self.assertNotEqual(alumno_a.school_id, alumno_b.school_id)
        self.assertEqual(alumno_a.id_alumno, alumno_b.id_alumno)

    def test_crear_alumno_rechaza_legajo_duplicado_en_mismo_colegio(self):
        Alumno.objects.create(
            school=self.school_a,
            nombre="Aina",
            apellido="Lopez",
            id_alumno="LEG600",
            curso="1A",
        )

        res = self.client.post(
            "/api/alumnos/crear/",
            {
                "id_alumno": "LEG600",
                "nombre": "Bruno",
                "apellido": "Suarez",
                "school_course_id": self.course_a_1a.id,
            },
            format="json",
            HTTP_X_SCHOOL=self.school_a.slug,
        )

        self.assertEqual(res.status_code, 400)
        self.assertIn("este colegio", res.json()["detail"])

    def test_crear_alumno_acepta_mismo_legajo_en_otro_colegio(self):
        Alumno.objects.create(
            school=self.school_a,
            nombre="Aina",
            apellido="Lopez",
            id_alumno="LEG700",
            curso="1A",
        )

        res = self.client.post(
            "/api/alumnos/crear/",
            {
                "id_alumno": "LEG700",
                "nombre": "Bruno",
                "apellido": "Suarez",
                "school_course_id": self.course_b_1a.id,
            },
            format="json",
            HTTP_X_SCHOOL=self.school_b.slug,
        )

        self.assertEqual(res.status_code, 201)
        alumno = Alumno.objects.get(pk=res.json()["alumno"]["id"])
        self.assertEqual(alumno.school_id, self.school_b.id)
        self.assertEqual(alumno.id_alumno, "LEG700")

    def test_generacion_automatica_de_legajo_se_scopea_por_colegio(self):
        Alumno.objects.create(
            school=self.school_a,
            nombre="Aina",
            apellido="Lopez",
            id_alumno="1A001",
            curso="1A",
        )

        res = self.client.post(
            "/api/alumnos/crear/",
            {
                "nombre": "Bruno",
                "apellido": "Suarez",
                "school_course_id": self.course_b_1a.id,
            },
            format="json",
            HTTP_X_SCHOOL=self.school_b.slug,
        )

        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["alumno"]["id_alumno"], "1A001")


@override_settings(SECURE_SSL_REDIRECT=False)
class ImportarAlumnosApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = _make_superuser("admin_importar_alumnos")
        self.regular = _make_user("regular_importar_alumnos")
        self.school = School.objects.create(name="Colegio Import", slug="colegio-import")
        self.course = SchoolCourse.objects.create(school=self.school, code="1A", name="Primero A", sort_order=1)

    def _csv_file(self, content: str):
        return SimpleUploadedFile(
            "alumnos.csv",
            content.encode("utf-8"),
            content_type="text/csv",
        )

    def _xlsx_file(self, rows: list[list[str]], *, sheets: dict[str, list[list[str]]] | None = None):
        from io import BytesIO

        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Hoja1"
        for row in rows:
            sheet.append(row)
        for title, sheet_rows in (sheets or {}).items():
            extra_sheet = workbook.create_sheet(title=title)
            for row in sheet_rows:
                extra_sheet.append(row)
        payload = BytesIO()
        workbook.save(payload)
        payload.seek(0)
        return SimpleUploadedFile(
            "alumnos.xlsx",
            payload.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_superuser_previsualiza_importacion_csv(self):
        self.client.force_authenticate(user=self.admin)

        res = self.client.post(
            "/api/admin/alumnos/import/",
            {
                "school": self.school.slug,
                "file": self._csv_file("legajo,nombre,apellido,curso\nIMP001,Luz,Perez,1A\n"),
            },
            format="multipart",
        )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["summary"]["valid"], 1)
        self.assertEqual(body["summary"]["created"], 0)
        self.assertFalse(Alumno.objects.filter(school=self.school, id_alumno="IMP001").exists())

    def test_superuser_confirma_importacion_csv(self):
        self.client.force_authenticate(user=self.admin)

        res = self.client.post(
            "/api/admin/alumnos/import/",
            {
                "school": self.school.slug,
                "commit": "true",
                "file": self._csv_file("legajo,nombre,apellido,curso\nIMP002,Noa,Diaz,1A\n"),
            },
            format="multipart",
        )

        self.assertEqual(res.status_code, 201)
        alumno = Alumno.objects.get(school=self.school, id_alumno="IMP002")
        self.assertEqual(alumno.school_course_id, self.course.id)
        self.assertEqual(alumno.nombre, "Noa")

    def test_importacion_rechaza_usuario_no_superuser(self):
        self.client.force_authenticate(user=self.regular)

        res = self.client.post(
            "/api/admin/alumnos/import/",
            {
                "school": self.school.slug,
                "file": self._csv_file("legajo,nombre,apellido,curso\nIMP003,Lia,Ruiz,1A\n"),
            },
            format="multipart",
        )

        self.assertEqual(res.status_code, 403)

    def test_superuser_previsualiza_xlsx_con_solo_apellidos(self):
        self.client.force_authenticate(user=self.admin)

        res = self.client.post(
            "/api/admin/alumnos/import/",
            {
                "school": self.school.slug,
                "file": self._xlsx_file(
                    [
                        ["apellidos", "curso"],
                        ["Perez", "1A"],
                        ["Diaz", "1A"],
                    ]
                ),
            },
            format="multipart",
        )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["summary"]["valid"], 2)
        self.assertEqual(body["summary"]["errors"], 0)
        self.assertEqual(body["preview"][0]["apellido"], "Perez")
        self.assertEqual(body["preview"][0]["nombre"], body["preview"][0]["legajo"])

    def test_superuser_previsualiza_xlsx_con_curso_en_nombre_de_hoja(self):
        self.client.force_authenticate(user=self.admin)
        SchoolCourse.objects.create(school=self.school, code="1B", name="Primero B", sort_order=2)

        res = self.client.post(
            "/api/admin/alumnos/import/",
            {
                "school": self.school.slug,
                "file": self._xlsx_file(
                    [
                        ["Nombre", "Apellido"],
                        ["Resumen", "General"],
                    ],
                    sheets={
                        "1A": [
                            ["Nombre", "Apellido"],
                            ["Luz", "Perez"],
                        ],
                        "1B": [
                            ["Nombre", "Apellido"],
                            ["Noa", "Diaz"],
                        ],
                    },
                ),
            },
            format="multipart",
        )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["summary"]["valid"], 2)
        self.assertEqual(body["summary"]["errors"], 0)
        self.assertEqual([item["curso"] for item in body["preview"]], ["1A", "1B"])


@override_settings(SECURE_SSL_REDIRECT=False)
class SchoolIntegrityGuardrailsTests(TestCase):
    def setUp(self):
        self.default_school = School.objects.get(slug="escuela-tecnova")
        self.default_course = SchoolCourse.objects.get(school=self.default_school, code="1A")
        self.preceptor = _make_user("preceptor_guardrails", ["Preceptores"])

    def test_alumno_nuevo_en_single_school_hereda_school_y_school_course(self):
        alumno = Alumno.objects.create(
            nombre="Lia",
            apellido="Perez",
            id_alumno="GUARD100",
            curso="1A",
        )

        self.assertEqual(alumno.school_id, self.default_school.id)
        self.assertEqual(alumno.school_course_id, self.default_course.id)

    def test_alumno_nuevo_sin_school_falla_si_hay_multiples_colegios(self):
        school_sur = School.objects.create(name="Colegio Guard Sur", slug="colegio-guard-sur")
        SchoolCourse.objects.create(school=school_sur, code="1A", name="1A Sur", sort_order=1)

        with self.assertRaises(ValidationError):
            Alumno.objects.create(
                nombre="Mia",
                apellido="Ruiz",
                id_alumno="GUARD200",
                curso="1A",
            )

    def test_asignacion_preceptor_sin_school_falla_si_hay_multiples_colegios(self):
        school_sur = School.objects.create(name="Colegio Guard Oeste", slug="colegio-guard-oeste")
        SchoolCourse.objects.create(school=school_sur, code="1A", name="1A Oeste", sort_order=1)

        with self.assertRaises(ValidationError):
            PreceptorCurso.objects.create(
                preceptor=self.preceptor,
                curso="1A",
            )

    def test_nota_nueva_hereda_school_del_alumno(self):
        alumno = Alumno.objects.create(
            school=self.default_school,
            nombre="Noa",
            apellido="Diaz",
            id_alumno="GUARD300",
            curso="1A",
        )

        nota = Nota.objects.create(
            alumno=alumno,
            materia="Lengua",
            tipo="Examen",
            calificacion="8",
            cuatrimestre=1,
        )

        self.assertEqual(nota.school_id, alumno.school_id)

    def test_bulk_asistencia_hereda_school_del_alumno(self):
        school_sur = School.objects.create(name="Colegio Guard Norte", slug="colegio-guard-norte")
        SchoolCourse.objects.create(school=school_sur, code="1A", name="1A Norte", sort_order=1)
        alumno = Alumno.objects.create(
            school=school_sur,
            nombre="Ivo",
            apellido="Lopez",
            id_alumno="GUARD400",
            curso="1A",
        )

        res = _bulk_upsert_asistencias(
            [alumno.id],
            timezone.localdate(),
            "clases",
            {
                alumno.id: {
                    "presente": False,
                    "tarde": False,
                }
            },
            school=None,
        )

        self.assertEqual(res["guardadas"], 1)
        asistencia = Asistencia.objects.get(alumno=alumno, fecha=timezone.localdate(), tipo_asistencia="clases")
        self.assertEqual(asistencia.school_id, school_sur.id)


@override_settings(SECURE_SSL_REDIRECT=False)
class VincularLegajoContractTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.school = School.objects.get(slug="escuela-tecnova")
        self.course, _ = SchoolCourse.objects.get_or_create(
            school=self.school,
            code="1A",
            defaults={
                "name": "Primero A Vincular",
                "sort_order": 1,
            },
        )
        self.user = _make_user("alumno_vincular_api")
        self.alumno = Alumno.objects.create(
            school=self.school,
            school_course=self.course,
            nombre="Luz",
            apellido="Perez",
            id_alumno="VINC100",
            curso="1A",
        )
        self.client.force_authenticate(user=self.user)

    def test_vincular_legajo_no_expone_wrapper_ok_al_crear_vinculo(self):
        res = self.client.post(
            "/api/alumnos/vincular/",
            {"id_alumno": self.alumno.id_alumno},
            format="json",
        )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertNotIn("ok", body)
        self.assertEqual(body["already_linked"], False)
        self.assertEqual(body["alumno"]["id"], self.alumno.id)

    def test_vincular_legajo_no_expone_wrapper_ok_si_ya_estaba_vinculado(self):
        self.alumno.usuario = self.user
        self.alumno.save(update_fields=["usuario"])

        res = self.client.post(
            "/api/alumnos/vincular/",
            {"id_alumno": self.alumno.id_alumno},
            format="json",
        )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertNotIn("ok", body)
        self.assertEqual(body["already_linked"], True)
        self.assertEqual(body["alumno"]["id"], self.alumno.id)
