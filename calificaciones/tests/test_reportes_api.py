from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.test import APIClient

from calificaciones.models import Alumno, Asistencia, Nota
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
        self.client = APIClient()

    def test_mis_estadisticas_padre_ve_solo_sus_hijos(self):
        padre_1 = _make_user("padre_1", ["Padres"])
        padre_2 = _make_user("padre_2", ["Padres"])

        alumno_1 = Alumno.objects.create(
            nombre="Ana",
            apellido="Perez",
            id_alumno="A001",
            curso="1A",
            padre=padre_1,
        )
        alumno_2 = Alumno.objects.create(
            nombre="Bruno",
            apellido="Lopez",
            id_alumno="B001",
            curso="1A",
            padre=padre_2,
        )

        Nota.objects.create(
            alumno=alumno_1,
            materia="Matemática",
            tipo="Examen",
            calificacion="10",
            cuatrimestre=1,
            fecha=date(2026, 1, 10),
        )
        Nota.objects.create(
            alumno=alumno_2,
            materia="Matemática",
            tipo="Examen",
            calificacion="2",
            cuatrimestre=1,
            fecha=date(2026, 1, 10),
        )

        Asistencia.objects.create(
            alumno=alumno_1,
            fecha=date(2026, 1, 11),
            tipo_asistencia="clases",
            presente=True,
            tarde=False,
        )
        Asistencia.objects.create(
            alumno=alumno_2,
            fecha=date(2026, 1, 11),
            tipo_asistencia="clases",
            presente=False,
            tarde=False,
        )

        self.client.force_authenticate(user=padre_1)
        res = self.client.get("/api/reportes/mis-estadisticas/")
        self.assertEqual(res.status_code, 200)

        body = res.json()
        self.assertEqual(body["rol"], "Padres")
        self.assertEqual(len(body["alumnos"]), 1)
        self.assertEqual(body["alumnos"][0]["id_alumno"], "A001")
        self.assertEqual(body["alumno_activo"]["id_alumno"], "A001")
        self.assertEqual(body["notas"]["promedio_general"], 10.0)

    def test_reporte_curso_preceptor_denegado_si_no_tiene_asignacion(self):
        preceptor = _make_user("preceptor_test", ["Preceptores"])
        PreceptorCurso.objects.create(preceptor=preceptor, curso="1A")

        self.client.force_authenticate(user=preceptor)
        res = self.client.get("/api/reportes/curso/2A/")
        self.assertEqual(res.status_code, 403)

    def test_reporte_curso_profesor_devuelve_json_agregado(self):
        profesor = _make_user("profesor_test", ["Profesores"])
        ProfesorCurso.objects.create(profesor=profesor, curso="1A")

        alumno = Alumno.objects.create(
            nombre="Carla",
            apellido="Diaz",
            id_alumno="C001",
            curso="1A",
        )
        Nota.objects.create(
            alumno=alumno,
            materia="Matemática",
            tipo="Examen",
            calificacion="8",
            cuatrimestre=1,
            fecha=date(2026, 1, 5),
        )
        Nota.objects.create(
            alumno=alumno,
            materia="Historia",
            tipo="Examen",
            calificacion="6",
            cuatrimestre=1,
            fecha=date(2026, 2, 5),
        )
        Asistencia.objects.create(
            alumno=alumno,
            fecha=date(2026, 1, 6),
            tipo_asistencia="clases",
            presente=True,
            tarde=False,
        )
        Asistencia.objects.create(
            alumno=alumno,
            fecha=date(2026, 1, 7),
            tipo_asistencia="informatica",
            presente=False,
            tarde=False,
        )
        Asistencia.objects.create(
            alumno=alumno,
            fecha=date(2026, 2, 7),
            tipo_asistencia="catequesis",
            presente=True,
            tarde=True,
        )

        self.client.force_authenticate(user=profesor)
        res = self.client.get("/api/reportes/curso/1A/")
        self.assertEqual(res.status_code, 200)

        body = res.json()
        self.assertEqual(body["scope"], "curso")
        self.assertEqual(body["rol"], "Profesores")
        self.assertEqual(body["curso"], "1A")
        self.assertIn("promedio_general", body["notas"])
        self.assertIn("promedios_por_materia", body["notas"])
        self.assertIn("distribucion_notas", body["notas"])
        self.assertIn("evolucion_mensual", body["notas"])
        self.assertIn("totales", body["asistencias"])
        self.assertIn("porcentaje_asistencia", body["asistencias"])
        self.assertIn("evolucion_mensual", body["asistencias"])

    def test_reporte_materia_profesor_denegado_para_curso_no_asignado(self):
        profesor = _make_user("profesor_curso", ["Profesores"])
        ProfesorCurso.objects.create(profesor=profesor, curso="1A")

        self.client.force_authenticate(user=profesor)
        res = self.client.get("/api/reportes/materia/Matemática/curso/2A/")
        self.assertEqual(res.status_code, 403)

