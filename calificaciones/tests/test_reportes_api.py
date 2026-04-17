from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from calificaciones.models import Alumno, Nota, School, SchoolCourse
from calificaciones.models_preceptores import PreceptorCurso, ProfesorCurso


def _make_user(username: str, groups: list[str]):
    User = get_user_model()
    user = User.objects.create_user(username=username, password="test1234")
    for name in groups:
        group, _ = Group.objects.get_or_create(name=name)
        user.groups.add(group)
    return user


class ReportesApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.school = School.objects.create(name="Colegio Reportes Base", slug="colegio-reportes-base")
        self.course_1a = SchoolCourse.objects.create(school=self.school, code="1A", name="1A", sort_order=1)
        self.course_2a = SchoolCourse.objects.create(school=self.school, code="2A", name="2A", sort_order=2)
        self.course_3b = SchoolCourse.objects.create(school=self.school, code="3B", name="3B", sort_order=3)

    def test_padre_no_puede_pedir_alumno_ajeno_en_mis_estadisticas(self):
        padre_1 = _make_user("padre_1", ["Padres"])
        padre_2 = _make_user("padre_2", ["Padres"])

        Alumno.objects.create(
            nombre="Ana",
            apellido="Perez",
            id_alumno="A001",
            school=self.school,
            school_course=self.course_1a,
            curso="1A",
            padre=padre_1,
        )
        alumno_ajeno = Alumno.objects.create(
            nombre="Bruno",
            apellido="Lopez",
            id_alumno="B001",
            school=self.school,
            school_course=self.course_1a,
            curso="1A",
            padre=padre_2,
        )

        self.client.force_authenticate(user=padre_1)
        res = self.client.get(
            f"/api/reportes/mis-estadisticas/?alumno_id={alumno_ajeno.id_alumno}",
            follow=True,
        )
        self.assertEqual(res.status_code, 403)

    def test_alumno_solo_ve_sus_datos(self):
        alumno_user_1 = _make_user("alumno_user_1", ["Alumnos"])
        _make_user("alumno_user_2", ["Alumnos"])

        alumno_1 = Alumno.objects.create(
            nombre="Carla",
            apellido="Diaz",
            id_alumno="C001",
            school=self.school,
            school_course=self.course_2a,
            curso="2A",
            usuario=alumno_user_1,
        )
        alumno_2 = Alumno.objects.create(
            nombre="Dario",
            apellido="Suarez",
            id_alumno="D001",
            school=self.school,
            school_course=self.course_2a,
            curso="2A",
        )

        Nota.objects.create(
            alumno=alumno_1,
            materia="Matemática",
            tipo="Examen",
            resultado="TEA",
            calificacion="TEA",
            cuatrimestre=1,
            fecha=date(2026, 1, 10),
        )
        Nota.objects.create(
            alumno=alumno_2,
            materia="Matemática",
            tipo="Examen",
            resultado="TEP",
            calificacion="TEP",
            cuatrimestre=1,
            fecha=date(2026, 1, 11),
        )

        self.client.force_authenticate(user=alumno_user_1)
        res = self.client.get("/api/reportes/mis-estadisticas/", follow=True)
        self.assertEqual(res.status_code, 200)

        body = res.json()
        self.assertEqual(body["alumno_activo"]["id_alumno"], "C001")
        self.assertEqual(body["alumno_activo"]["school_course_name"], "2A")
        self.assertNotIn("curso", body["alumno_activo"])
        self.assertEqual(body["resumen_notas"]["total_evaluaciones"], 1)
        self.assertEqual(body["resumen_notas"]["conteos_por_estado"]["TEA"], 1)

    def test_json_incluye_conteos_y_evolucion_con_estados(self):
        profesor = _make_user("profesor_test", ["Profesores"])
        ProfesorCurso.objects.create(
            school=self.school,
            school_course=self.course_1a,
            profesor=profesor,
            curso="1A",
        )

        alumno = Alumno.objects.create(
            nombre="Elena",
            apellido="Mora",
            id_alumno="E001",
            school=self.school,
            school_course=self.course_1a,
            curso="1A",
        )
        Nota.objects.create(
            alumno=alumno,
            materia="Matemática",
            tipo="Examen",
            resultado="TEA",
            calificacion="TEA",
            cuatrimestre=1,
            fecha=date(2026, 1, 5),
        )
        Nota.objects.create(
            alumno=alumno,
            materia="Matemática",
            tipo="Trabajo Práctico",
            resultado="TEP",
            calificacion="TEP",
            cuatrimestre=1,
            fecha=date(2026, 1, 20),
        )
        Nota.objects.create(
            alumno=alumno,
            materia="Historia",
            tipo="Examen",
            resultado="TED",
            calificacion="TED",
            cuatrimestre=1,
            fecha=date(2026, 2, 3),
        )

        self.client.force_authenticate(user=profesor)
        res = self.client.get(
            f"/api/reportes/curso/{self.course_1a.id}/",
            {"school": self.school.slug},
            follow=True,
        )
        self.assertEqual(res.status_code, 200)

        body = res.json()
        self.assertIn("resumen_notas", body)
        self.assertIn("conteos_por_estado", body["resumen_notas"])
        self.assertEqual(set(body["resumen_notas"]["conteos_por_estado"].keys()), {"TEA", "TEP", "TED"})

        self.assertIn("evolucion_mensual_notas", body)
        self.assertGreaterEqual(len(body["evolucion_mensual_notas"]), 1)
        primer_mes = body["evolucion_mensual_notas"][0]
        self.assertIn("TEA_count", primer_mes)
        self.assertIn("TEP_count", primer_mes)
        self.assertIn("TED_count", primer_mes)

    def test_reporte_por_curso_rechaza_codigo_legacy_en_path(self):
        profesor = _make_user("profesor_test_legacy", ["Profesores"])
        ProfesorCurso.objects.create(
            school=self.school,
            school_course=self.course_1a,
            profesor=profesor,
            curso="1A",
        )
        self.client.force_authenticate(user=profesor)

        res = self.client.get(
            "/api/reportes/curso/1A/",
            {"school": self.school.slug},
            follow=True,
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            res.json()["detail"],
            "El código legacy de curso en la ruta está deprecado. Usa school_course_id.",
        )

    def test_directivo_puede_ver_reportes_de_cualquier_curso(self):
        directivo = _make_user("directivo_test", ["Directivos"])

        alumno = Alumno.objects.create(
            nombre="Nora",
            apellido="Silva",
            id_alumno="N001",
            school=self.school,
            school_course=self.course_3b,
            curso="3B",
        )
        Nota.objects.create(
            alumno=alumno,
            materia="Historia",
            tipo="Examen",
            resultado="TEA",
            calificacion="TEA",
            cuatrimestre=1,
            fecha=date(2026, 3, 2),
        )

        self.client.force_authenticate(user=directivo)
        res = self.client.get(
            f"/api/reportes/curso/{self.course_3b.id}/",
            {"school": self.school.slug},
            follow=True,
        )
        self.assertEqual(res.status_code, 200)

        body = res.json()
        self.assertEqual(body["rol"], "Directivos")
        self.assertNotIn("curso", body)
        self.assertEqual(body["resumen_notas"]["total_evaluaciones"], 1)

    def test_profesor_puede_ver_historico_de_un_alumno_del_curso(self):
        profesor = _make_user("profesor_historico", ["Profesores"])
        ProfesorCurso.objects.create(
            school=self.school,
            school_course=self.course_1a,
            profesor=profesor,
            curso="1A",
        )

        alumno = Alumno.objects.create(
            nombre="Julia",
            apellido="Ramos",
            id_alumno="J001",
            school=self.school,
            school_course=self.course_1a,
            curso="1A",
        )
        otro_alumno = Alumno.objects.create(
            nombre="Kevin",
            apellido="Sosa",
            id_alumno="K001",
            school=self.school,
            school_course=self.course_1a,
            curso="1A",
        )

        Nota.objects.create(
            school=self.school,
            alumno=alumno,
            materia="Matemática",
            tipo="Examen",
            resultado="TEA",
            calificacion="8",
            nota_numerica=8,
            cuatrimestre=1,
            fecha=date(2026, 3, 10),
        )
        Nota.objects.create(
            school=self.school,
            alumno=alumno,
            materia="Historia",
            tipo="Trabajo Práctico",
            resultado="TEP",
            calificacion="5",
            nota_numerica=5,
            cuatrimestre=1,
            fecha=date(2026, 4, 5),
        )
        Nota.objects.create(
            school=self.school,
            alumno=otro_alumno,
            materia="Historia",
            tipo="Examen",
            resultado="TED",
            calificacion="TED",
            cuatrimestre=1,
            fecha=date(2026, 4, 6),
        )

        self.client.force_authenticate(user=profesor)
        res = self.client.get(
            f"/api/reportes/curso/{self.course_1a.id}/",
            {"school": self.school.slug, "alumno_id": alumno.id},
            follow=True,
        )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["scope"], "alumno_historico")
        self.assertEqual(body["alumno_activo"]["id_alumno"], "J001")
        self.assertEqual(body["resumen_notas"]["total_evaluaciones"], 2)
        self.assertEqual(len(body["historial_detallado"]), 2)
        self.assertEqual(body["historial_detallado"][0]["fecha"], "2026-04-05")
        self.assertEqual(body["promedio_general_numerico"], 6.5)
        self.assertEqual(body["evolucion_mensual_notas"][0]["promedio_numerico"], 8.0)
        self.assertEqual(body["evolucion_mensual_notas"][1]["promedio_numerico"], 5.0)

    def test_reporte_historico_rechaza_alumno_fuera_del_curso(self):
        profesor = _make_user("profesor_historico_invalid", ["Profesores"])
        ProfesorCurso.objects.create(
            school=self.school,
            school_course=self.course_1a,
            profesor=profesor,
            curso="1A",
        )

        alumno_otro_curso = Alumno.objects.create(
            nombre="Laura",
            apellido="Mendez",
            id_alumno="L001",
            school=self.school,
            school_course=self.course_2a,
            curso="2A",
        )

        self.client.force_authenticate(user=profesor)
        res = self.client.get(
            f"/api/reportes/curso/{self.course_1a.id}/",
            {"school": self.school.slug, "alumno_id": alumno_otro_curso.id},
            follow=True,
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["detail"], "El alumno no pertenece al curso seleccionado.")

    def test_historico_alumno_expone_comparativa_anual_y_permite_filtrar_un_anio(self):
        profesor = _make_user("profesor_historico_anual", ["Profesores"])
        ProfesorCurso.objects.create(
            school=self.school,
            school_course=self.course_1a,
            profesor=profesor,
            curso="1A",
        )

        alumno = Alumno.objects.create(
            nombre="Mia",
            apellido="Neri",
            id_alumno="M001",
            school=self.school,
            school_course=self.course_1a,
            curso="1A",
        )
        Nota.objects.create(
            school=self.school,
            alumno=alumno,
            materia="Matemática",
            tipo="Examen",
            resultado="TEA",
            calificacion="8",
            nota_numerica=8,
            cuatrimestre=1,
            fecha=date(2025, 5, 10),
        )
        Nota.objects.create(
            school=self.school,
            alumno=alumno,
            materia="Matemática",
            tipo="Examen",
            resultado="TEP",
            calificacion="5",
            nota_numerica=5,
            cuatrimestre=1,
            fecha=date(2026, 5, 10),
        )

        self.client.force_authenticate(user=profesor)
        res = self.client.get(
            f"/api/reportes/curso/{self.course_1a.id}/",
            {"school": self.school.slug, "alumno_id": alumno.id, "anio": 2026},
            follow=True,
        )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["filtros"]["anio"], 2026)
        self.assertEqual(body["resumen_notas"]["total_evaluaciones"], 1)
        self.assertEqual(body["historial_detallado"][0]["fecha"], "2026-05-10")
        self.assertEqual(body["anios_disponibles"], [2025, 2026])
        self.assertEqual(len(body["historial_anual"]), 2)


class ReportesSchoolScopingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.profesor = _make_user("profesor_reportes_school", ["Profesores"])
        self.profesor_sin_asignacion = _make_user("profesor_reportes_sin_asignacion", ["Profesores"])
        self.preceptor = _make_user("preceptor_reportes_school", ["Preceptores"])
        self.preceptor_sin_asignacion = _make_user("preceptor_reportes_sin_asignacion", ["Preceptores"])
        self.school_a = School.objects.create(name="Colegio Reportes Norte", slug="colegio-reportes-norte")
        self.school_b = School.objects.create(name="Colegio Reportes Sur", slug="colegio-reportes-sur")
        self.course_a1 = SchoolCourse.objects.create(school=self.school_a, code="1A", name="1A Norte", sort_order=1)
        self.course_b1 = SchoolCourse.objects.create(school=self.school_b, code="1A", name="1A Sur", sort_order=1)
        ProfesorCurso.objects.create(school=self.school_a, profesor=self.profesor, curso="1A")
        PreceptorCurso.objects.create(school=self.school_a, preceptor=self.preceptor, curso="1A")

        self.alumno_a = Alumno.objects.create(
            school=self.school_a,
            nombre="Lia",
            apellido="Perez",
            id_alumno="RNS001",
            curso="1A",
        )
        self.alumno_b = Alumno.objects.create(
            school=self.school_b,
            nombre="Milo",
            apellido="Ruiz",
            id_alumno="RSS001",
            curso="1A",
        )
        Nota.objects.create(
            school=self.school_a,
            alumno=self.alumno_a,
            materia="Matemática",
            tipo="Examen",
            resultado="TEA",
            calificacion="TEA",
            cuatrimestre=1,
            fecha=date(2026, 3, 5),
        )
        Nota.objects.create(
            school=self.school_b,
            alumno=self.alumno_b,
            materia="Matemática",
            tipo="Examen",
            resultado="TEP",
            calificacion="TEP",
            cuatrimestre=1,
            fecha=date(2026, 3, 6),
        )

    def test_profesor_reporte_por_curso_filtra_por_school_activo(self):
        self.client.force_authenticate(user=self.profesor)

        res = self.client.get(
            f"/api/reportes/curso/{self.course_a1.id}/",
            {"school": self.school_a.slug},
            follow=True,
        )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["resumen_notas"]["total_evaluaciones"], 1)
        self.assertEqual(body["resumen_notas"]["conteos_por_estado"]["TEA"], 1)
        self.assertEqual(body["resumen_notas"]["conteos_por_estado"]["TEP"], 0)

    def test_profesor_reporte_por_curso_acepta_school_course_id_en_path(self):
        self.client.force_authenticate(user=self.profesor)

        res = self.client.get(
            f"/api/reportes/curso/{self.course_a1.id}/",
            {"school": self.school_a.slug},
            follow=True,
        )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertNotIn("curso", body)
        self.assertEqual(body["school_course_id"], self.course_a1.id)
        self.assertEqual(body["school_course_name"], "1A Norte")
        self.assertEqual(body["resumen_notas"]["total_evaluaciones"], 1)
        self.assertEqual(body["resumen_notas"]["conteos_por_estado"]["TEA"], 1)
        self.assertEqual(body["resumen_notas"]["conteos_por_estado"]["TEP"], 0)

    def test_preceptor_reporte_por_curso_filtra_por_school_activo(self):
        self.client.force_authenticate(user=self.preceptor)

        res = self.client.get(
            f"/api/reportes/curso/{self.course_a1.id}/",
            {"school": self.school_a.slug},
            follow=True,
        )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["resumen_notas"]["total_evaluaciones"], 1)
        self.assertEqual(body["resumen_notas"]["conteos_por_estado"]["TEA"], 1)
        self.assertEqual(body["resumen_notas"]["conteos_por_estado"]["TEP"], 0)

    def test_reporte_por_curso_rechaza_codigo_legacy_en_path_con_school_activo(self):
        self.client.force_authenticate(user=self.profesor)

        res = self.client.get(
            "/api/reportes/curso/1A/",
            {"school": self.school_a.slug},
            follow=True,
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            res.json()["detail"],
            "El código legacy de curso en la ruta está deprecado. Usa school_course_id.",
        )

    def test_reporte_por_materia_y_curso_rechaza_codigo_legacy_en_path(self):
        self.client.force_authenticate(user=self.profesor)

        res = self.client.get(
            "/api/reportes/materia/Matemática/curso/1A/",
            {"school": self.school_a.slug},
            follow=True,
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            res.json()["detail"],
            "El código legacy de curso en la ruta está deprecado. Usa school_course_id.",
        )

    def test_profesor_sin_asignacion_no_puede_ver_reporte_por_curso(self):
        self.client.force_authenticate(user=self.profesor_sin_asignacion)

        res = self.client.get(
            f"/api/reportes/curso/{self.course_a1.id}/",
            {"school": self.school_a.slug},
            follow=True,
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No tenes cursos asignados.")

    def test_preceptor_sin_asignacion_no_puede_ver_reporte_por_curso(self):
        self.client.force_authenticate(user=self.preceptor_sin_asignacion)

        res = self.client.get(
            f"/api/reportes/curso/{self.course_a1.id}/",
            {"school": self.school_a.slug},
            follow=True,
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No tenes cursos asignados.")

    def test_profesor_sin_asignacion_no_puede_ver_reporte_por_materia_y_curso(self):
        self.client.force_authenticate(user=self.profesor_sin_asignacion)

        res = self.client.get(
            f"/api/reportes/materia/Matemática/curso/{self.course_a1.id}/",
            {"school": self.school_a.slug},
            follow=True,
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No tenes cursos asignados.")
