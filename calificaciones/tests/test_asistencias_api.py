from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.test.utils import override_settings
from rest_framework.test import APIClient

from calificaciones.models import Alumno, Asistencia, Notificacion, AlertaInasistencia
from calificaciones.models_preceptores import PreceptorCurso


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


@override_settings(SECURE_SSL_REDIRECT=False)
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

    def test_dos_ausencias_consecutivas_crea_alerta_inasistencia(self):
        staff = _make_staff_user("staff_alerta_inas")
        alumno = _make_alumno("Lia", "Suarez", "LEG301", curso="1A")
        self.client.force_authenticate(user=staff)

        p1 = {
            "curso": "1A",
            "fecha": "2026-03-01",
            "tipo_asistencia": "clases",
            "asistencias": {str(alumno.id): "ausente"},
        }
        p2 = {
            "curso": "1A",
            "fecha": "2026-03-02",
            "tipo_asistencia": "clases",
            "asistencias": {str(alumno.id): "ausente"},
        }

        r1 = self.client.post("/api/asistencias/registrar/", p1, format="json")
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(AlertaInasistencia.objects.count(), 0)

        r2 = self.client.post("/api/asistencias/registrar/", p2, format="json")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(AlertaInasistencia.objects.count(), 1)

        alerta = AlertaInasistencia.objects.first()
        self.assertEqual(alerta.alumno_id, alumno.id)
        self.assertEqual(alerta.motivo, "AUSENCIAS_CONSECUTIVAS")
        self.assertEqual(alerta.estado, "activa")

    def test_endpoint_preceptor_alertas_inasistencias_lista_alumno(self):
        User = get_user_model()
        preceptor = User.objects.create_user(username="preceptor_inas", password="test1234")
        grp, _ = Group.objects.get_or_create(name="Preceptores")
        preceptor.groups.add(grp)

        alumno = _make_alumno("Noa", "Garcia", "LEG401", curso="1A")
        PreceptorCurso.objects.create(preceptor=preceptor, curso="1A")

        AlertaInasistencia.objects.create(
            alumno=alumno,
            curso="1A",
            tipo_asistencia="clases",
            motivo="AUSENCIAS_CONSECUTIVAS",
            severidad=1,
            valor_actual=2,
            umbral=2,
            estado="activa",
        )

        self.client.force_authenticate(user=preceptor)
        res = self.client.get("/api/preceptor/alertas-inasistencias/?limit=10")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("results", body)
        self.assertGreaterEqual(len(body["results"]), 1)
        self.assertEqual(body["results"][0]["alumno"]["id"], alumno.id)
        self.assertIn("total_inasistencias_clases", body["results"][0])

    @override_settings(ALERTAS_INASISTENCIAS_UMBRALES_FALTAS="10,20,25")
    def test_alerta_faltas_acumuladas_al_llegar_a_10(self):
        staff = _make_staff_user("staff_faltas_10")
        alumno = _make_alumno("Mia", "Lopez", "LEG501", curso="1A")
        self.client.force_authenticate(user=staff)

        base = date(2026, 3, 1)
        for i in range(10):
            payload = {
                "curso": "1A",
                "fecha": str(base + timedelta(days=i)),
                "tipo_asistencia": "clases",
                "asistencias": {str(alumno.id): "ausente"},
            }
            res = self.client.post("/api/asistencias/registrar/", payload, format="json")
            self.assertEqual(res.status_code, 200)

        self.assertTrue(
            AlertaInasistencia.objects.filter(
                alumno=alumno,
                motivo="FALTAS_ACUMULADAS",
                umbral=10,
            ).exists()
        )
