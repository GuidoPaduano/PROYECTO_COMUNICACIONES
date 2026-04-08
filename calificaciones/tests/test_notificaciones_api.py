from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from calificaciones.models import Notificacion, School


@override_settings(SECURE_SSL_REDIRECT=False)
class NotificacionesApiContractTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="notif_contract_user",
            password="test1234",
        )
        self.other_user = get_user_model().objects.create_user(
            username="notif_contract_other",
            password="test1234",
        )
        self.school = School.objects.create(name="Colegio Notifs", slug="colegio-notifs")

        self.notif_1 = Notificacion.objects.create(
            school=self.school,
            destinatario=self.user,
            tipo="mensaje",
            titulo="Mensaje 1",
            descripcion="Primera notificacion",
            leida=False,
        )
        self.notif_2 = Notificacion.objects.create(
            school=self.school,
            destinatario=self.user,
            tipo="evento",
            titulo="Evento 1",
            descripcion="Segunda notificacion",
            leida=False,
        )
        Notificacion.objects.create(
            school=self.school,
            destinatario=self.other_user,
            tipo="nota",
            titulo="Nota ajena",
            descripcion="No debe tocarse",
            leida=False,
        )

    def test_marcar_leida_no_expone_wrapper_success(self):
        self.client.force_authenticate(user=self.user)

        res = self.client.post(f"/api/notificaciones/{self.notif_1.id}/marcar_leida/")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"updated": 1})
        self.notif_1.refresh_from_db()
        self.assertTrue(self.notif_1.leida)

    def test_marcar_todas_leidas_no_expone_wrapper_success(self):
        self.client.force_authenticate(user=self.user)

        res = self.client.post("/api/notificaciones/marcar_todas_leidas/")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"updated": 2})
        self.notif_1.refresh_from_db()
        self.notif_2.refresh_from_db()
        self.assertTrue(self.notif_1.leida)
        self.assertTrue(self.notif_2.leida)
        self.assertFalse(
            Notificacion.objects.get(destinatario=self.other_user).leida
        )

    def test_recientes_y_unread_count_siguen_filtrando_por_destinatario(self):
        self.client.force_authenticate(user=self.user)

        recent = self.client.get("/api/notificaciones/recientes/?solo_no_leidas=1&limit=5")
        unread = self.client.get("/api/notificaciones/unread_count/")

        self.assertEqual(recent.status_code, 200)
        self.assertEqual(unread.status_code, 200)
        self.assertEqual(unread.json(), {"count": 2})
        payload = recent.json()
        self.assertEqual(len(payload), 2)
        self.assertEqual({item["id"] for item in payload}, {self.notif_1.id, self.notif_2.id})
