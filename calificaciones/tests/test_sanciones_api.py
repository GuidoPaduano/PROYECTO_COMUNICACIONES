from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from calificaciones.models import Alumno, Sancion


def _make_user(username: str, groups: list[str] | None = None):
    User = get_user_model()
    user = User.objects.create_user(username=username, password="test1234")
    for name in groups or []:
        group, _ = Group.objects.get_or_create(name=name)
        user.groups.add(group)
    return user


@override_settings(SECURE_SSL_REDIRECT=False)
class FirmaSancionApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.padre = _make_user("padre_firma_sancion", ["Padres"])
        self.padre_otro = _make_user("padre_otro_sancion", ["Padres"])
        self.alumno = Alumno.objects.create(
            nombre="Eva",
            apellido="Suarez",
            id_alumno="LEG551",
            curso="1A",
            padre=self.padre,
        )
        self.sancion = Sancion.objects.create(
            alumno=self.alumno,
            tipo="Amonestación",
            motivo="Incumplimiento del reglamento",
            fecha="2026-03-11",
            docente="Preceptor 1",
        )

    def test_padre_puede_firmar_sancion_una_vez(self):
        self.client.force_authenticate(user=self.padre)

        res = self.client.post(f"/api/sanciones/{self.sancion.id}/firmar/", format="json")

        self.assertEqual(res.status_code, 200)
        self.sancion.refresh_from_db()
        self.assertTrue(self.sancion.firmada)
        self.assertEqual(self.sancion.firmada_por_id, self.padre.id)
        self.assertIsNotNone(self.sancion.firmada_en)

    def test_padre_no_puede_firmar_sancion_dos_veces(self):
        self.client.force_authenticate(user=self.padre)
        first = self.client.post(f"/api/sanciones/{self.sancion.id}/firmar/", format="json")
        self.assertEqual(first.status_code, 200)

        second = self.client.post(f"/api/sanciones/{self.sancion.id}/firmar/", format="json")

        self.assertEqual(second.status_code, 400)
        self.sancion.refresh_from_db()
        self.assertTrue(self.sancion.firmada)

    def test_otro_padre_no_puede_firmar_sancion(self):
        self.client.force_authenticate(user=self.padre_otro)

        res = self.client.post(f"/api/sanciones/{self.sancion.id}/firmar/", format="json")

        self.assertEqual(res.status_code, 403)
        self.sancion.refresh_from_db()
        self.assertFalse(self.sancion.firmada)
