from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from calificaciones.models import Alumno, Asistencia, Notificacion


def _make_staff_user(username="staff"):
    User = get_user_model()
    return User.objects.create_user(
        username=username,
        password="test1234",
        is_staff=True,
        is_superuser=False,
    )


def _make_alumno(nombre, apellido, legajo, curso="1A", padre=None):
    return Alumno.objects.create(
        nombre=nombre,
        apellido=apellido,
        id_alumno=legajo,
        curso=curso,
        padre=padre,
    )


class AsistenciasApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_registrar_asistencias_formato_c_map(self):
        staff = _make_staff_user("staff_map")
        a1 = _make_alumno("Ana", "Perez", "LEG001", curso="1A")
        a2 = _make_alumno("Beto", "Lopez", "LEG002", curso="1A")

        self.client.force_authenticate(user=staff)

        payload = {
            "curso": "1A",
            "fecha": str(date.today()),
            "tipo_asistencia": "clases",
            "asistencias": {
                str(a1.id): "ausente",
                str(a2.id): "presente",
            },
        }

        res = self.client.post("/api/asistencias/registrar/", payload, format="json")
        self.assertEqual(res.status_code, 200)

        r1 = Asistencia.objects.get(alumno=a1, fecha=date.today(), tipo_asistencia="clases")
        r2 = Asistencia.objects.get(alumno=a2, fecha=date.today(), tipo_asistencia="clases")
        self.assertFalse(r1.presente)
        self.assertTrue(r2.presente)

    def test_registrar_asistencias_formato_a_presentes_tardes(self):
        staff = _make_staff_user("staff_a")
        a1 = _make_alumno("Ciro", "Diaz", "LEG101", curso="1A")
        a2 = _make_alumno("Dani", "Suarez", "LEG102", curso="1A")

        self.client.force_authenticate(user=staff)

        payload = {
            "curso": "1A",
            "fecha": str(date.today()),
            "tipo_asistencia": "clases",
            "presentes": [a1.id],
            "tardes": [a2.id],
        }

        res = self.client.post("/api/asistencias/registrar/", payload, format="json")
        self.assertEqual(res.status_code, 200)

        r1 = Asistencia.objects.get(alumno=a1, fecha=date.today(), tipo_asistencia="clases")
        r2 = Asistencia.objects.get(alumno=a2, fecha=date.today(), tipo_asistencia="clases")
        self.assertTrue(r1.presente)
        self.assertFalse(r1.tarde)
        self.assertTrue(r2.presente)
        self.assertTrue(r2.tarde)

    def test_inasistencia_crea_notificacion_a_padre(self):
        User = get_user_model()
        padre = User.objects.create_user(username="padretest", password="test1234")
        staff = _make_staff_user("staff_notif")
        alumno = _make_alumno("Eva", "Gomez", "LEG201", curso="1A", padre=padre)

        self.client.force_authenticate(user=staff)

        payload = {
            "curso": "1A",
            "fecha": str(date.today()),
            "tipo_asistencia": "clases",
            "asistencias": {str(alumno.id): "ausente"},
        }

        res = self.client.post("/api/asistencias/registrar/", payload, format="json")
        self.assertEqual(res.status_code, 200)

        self.assertTrue(
            Notificacion.objects.filter(destinatario=padre, tipo="inasistencia").exists()
        )
