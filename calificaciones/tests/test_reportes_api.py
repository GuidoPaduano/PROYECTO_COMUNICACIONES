from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.test import APIClient

from calificaciones.models import Alumno, Nota
from calificaciones.models_preceptores import ProfesorCurso


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

    def test_padre_no_puede_pedir_alumno_ajeno_en_mis_estadisticas(self):
        padre_1 = _make_user("padre_1", ["Padres"])
        padre_2 = _make_user("padre_2", ["Padres"])

        Alumno.objects.create(
            nombre="Ana",
            apellido="Perez",
            id_alumno="A001",
            curso="1A",
            padre=padre_1,
        )
        alumno_ajeno = Alumno.objects.create(
            nombre="Bruno",
            apellido="Lopez",
            id_alumno="B001",
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
            curso="2A",
            usuario=alumno_user_1,
        )
        alumno_2 = Alumno.objects.create(
            nombre="Dario",
            apellido="Suarez",
            id_alumno="D001",
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
        self.assertEqual(body["resumen_notas"]["total_evaluaciones"], 1)
        self.assertEqual(body["resumen_notas"]["conteos_por_estado"]["TEA"], 1)

    def test_json_incluye_conteos_y_evolucion_con_estados(self):
        profesor = _make_user("profesor_test", ["Profesores"])
        ProfesorCurso.objects.create(profesor=profesor, curso="1A")

        alumno = Alumno.objects.create(
            nombre="Elena",
            apellido="Mora",
            id_alumno="E001",
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
        res = self.client.get("/api/reportes/curso/1A/", follow=True)
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
