from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.test.utils import override_settings
from rest_framework.test import APIClient

from calificaciones.models import AlertaAcademica, Alumno, Notificacion
from calificaciones.models_preceptores import PreceptorCurso


def _make_user(username: str, groups: list[str] | None = None, *, is_staff: bool = False):
    User = get_user_model()
    user = User.objects.create_user(username=username, password="test1234", is_staff=is_staff)
    for name in groups or []:
        group, _ = Group.objects.get_or_create(name=name)
        user.groups.add(group)
    return user


@override_settings(SECURE_SSL_REDIRECT=False)
class AlertasAcademicasApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.profesor = _make_user("profe_alertas", ["Profesores"], is_staff=True)
        self.padre = _make_user("padre_alertas", ["Padres"])
        self.preceptor = _make_user("preceptor_alertas", ["Preceptores"])

        self.alumno = Alumno.objects.create(
            nombre="Luz",
            apellido="Perez",
            id_alumno="LEG900",
            curso="1A",
            padre=self.padre,
        )
        PreceptorCurso.objects.create(preceptor=self.preceptor, curso="1A")
        self.client.force_authenticate(user=self.profesor)

    def _post_nota(self, *, resultado: str, calificacion: str, fecha_iso: str, materia: str = "Lengua"):
        payload = {
            "alumno": self.alumno.id,
            "materia": materia,
            "tipo": "Examen",
            "resultado": resultado,
            "calificacion": calificacion,
            "cuatrimestre": 1,
            "fecha": fecha_iso,
        }
        return self.client.post("/api/calificaciones/notas/", payload, format="json")

    def test_ted_crea_alerta_y_notifica_a_padre_y_preceptor(self):
        res = self._post_nota(resultado="TED", calificacion="TED", fecha_iso="2026-03-01")
        self.assertEqual(res.status_code, 201)

        self.assertEqual(AlertaAcademica.objects.count(), 1)
        alerta = AlertaAcademica.objects.first()
        self.assertEqual(alerta.severidad, 1)

        notifs = Notificacion.objects.filter(tipo="otro", meta__es_alerta_academica=True)
        dest_ids = {n.destinatario_id for n in notifs}
        self.assertIn(self.padre.id, dest_ids)
        self.assertIn(self.preceptor.id, dest_ids)

    def test_cooldown_7_dias_bloquea_alerta_repetida(self):
        res1 = self._post_nota(resultado="TED", calificacion="TED", fecha_iso="2026-03-01")
        self.assertEqual(res1.status_code, 201)
        self.assertEqual(AlertaAcademica.objects.count(), 1)

        res2 = self._post_nota(resultado="TED", calificacion="TED", fecha_iso="2026-03-02")
        self.assertEqual(res2.status_code, 201)
        self.assertEqual(AlertaAcademica.objects.count(), 1)

    def test_racha_de_dos_malas_dispara_alerta(self):
        r1 = self._post_nota(resultado="TEA", calificacion="TEA", fecha_iso="2026-03-01", materia="Historia")
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(AlertaAcademica.objects.count(), 0)

        r2 = self._post_nota(resultado="TEP", calificacion="TEP", fecha_iso="2026-03-02", materia="Historia")
        self.assertEqual(r2.status_code, 201)
        self.assertEqual(AlertaAcademica.objects.count(), 0)

        r3 = self._post_nota(resultado="TEP", calificacion="TEP", fecha_iso="2026-03-03", materia="Historia")
        self.assertEqual(r3.status_code, 201)
        self.assertEqual(AlertaAcademica.objects.count(), 1)

    def test_preceptor_endpoint_lista_alumnos_en_alerta(self):
        self._post_nota(resultado="TED", calificacion="TED", fecha_iso="2026-03-01", materia="Lengua")

        self.client.force_authenticate(user=self.preceptor)
        res = self.client.get("/api/preceptor/alertas-academicas/?limit=10")
        self.assertEqual(res.status_code, 200)

        body = res.json()
        self.assertIn("results", body)
        self.assertGreaterEqual(len(body["results"]), 1)

        row = body["results"][0]
        self.assertEqual(row["alumno"]["id"], self.alumno.id)
        self.assertEqual(row["alumno"]["curso"], "1A")
