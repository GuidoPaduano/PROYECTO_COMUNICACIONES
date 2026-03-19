from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.test import Client
from rest_framework.test import APIClient

from calificaciones.models import Alumno, Nota
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
class AccessControlSecurityTests(TestCase):
    def setUp(self):
        self.api_client = APIClient()
        self.web_client = Client()
        self.profesor = _make_user("profe_roster", ["Profesores"])
        self.preceptor = _make_user("preceptor_roster", ["Preceptores"])
        self.padre = _make_user("padre_roster", ["Padres"])
        self.padre_otro = _make_user("padre_otro", ["Padres"])
        self.alumno_user = _make_user("alumno_roster", ["Alumnos"])
        self.alumno = Alumno.objects.create(
            nombre="Ana",
            apellido="Lopez",
            id_alumno="LEG900",
            curso="1A",
            padre=self.padre,
            usuario=self.alumno_user,
        )
        ProfesorCurso.objects.create(profesor=self.profesor, curso="1A")
        PreceptorCurso.objects.create(preceptor=self.preceptor, curso="1A")

    def test_padre_no_puede_listar_alumnos_de_un_curso(self):
        self.api_client.force_authenticate(user=self.padre)

        res = self.api_client.get("/api/alumnos/", {"curso": "1A"})

        self.assertEqual(res.status_code, 403)

    def test_preceptor_puede_listar_alumnos_de_su_curso(self):
        self.api_client.force_authenticate(user=self.preceptor)

        res = self.api_client.get("/api/alumnos/", {"curso": "1A"})

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
