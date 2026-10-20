from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from calificaciones.models import CarpetaMensajes, Mensaje, School, SchoolCourse
from calificaciones.models_preceptores import SchoolMembership


@override_settings(SECURE_SSL_REDIRECT=False)
class MessageFolderTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        users = get_user_model().objects
        self.teacher = users.create_user(username="folder_teacher", password="test1234")
        self.parent = users.create_user(username="folder_parent", password="test1234")
        self.school = School.objects.create(name="Folder School", slug="folder-school")
        SchoolMembership.objects.create(school=self.school, user=self.teacher)
        SchoolMembership.objects.create(school=self.school, user=self.parent)
        SchoolCourse.objects.create(school=self.school, code="1A", name="1A")
        self.first = Mensaje.objects.create(
            school=self.school, remitente=self.parent, destinatario=self.teacher,
            curso="1A", asunto="Consulta", contenido="Primer mensaje",
        )
        self.second = Mensaje.objects.create(
            school=self.school, remitente=self.parent, destinatario=self.teacher,
            curso="1A", asunto="Consulta", contenido="Segundo mensaje",
        )

    def test_move_applies_to_the_whole_conversation_and_future_messages(self):
        self.client.force_authenticate(user=self.teacher)
        created = self.client.post("/api/mensajes/carpetas", {"nombre": "Familias"}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        folder_id = created.json()["id"]
        moved = self.client.post(
            f"/api/mensajes/{self.first.id}/mover", {"carpeta_id": folder_id}, format="json"
        )
        self.assertEqual(moved.status_code, 200)
        self.assertEqual(
            {item["carpeta_id"] for item in self.client.get("/api/mensajes/recibidos/").json()},
            {folder_id},
        )
        third = Mensaje.objects.create(
            school=self.school, remitente=self.parent, destinatario=self.teacher,
            curso="1A", asunto="Re: Consulta", contenido="Respuesta nueva",
        )
        inbox = self.client.get("/api/mensajes/recibidos/").json()
        self.assertEqual(next(item for item in inbox if item["id"] == third.id)["carpeta_id"], folder_id)

        self.client.force_authenticate(user=self.parent)
        self.assertEqual(self.client.get("/api/mensajes/carpetas/").json(), [])
        self.assertEqual(
            self.client.post(f"/api/mensajes/{self.first.id}/mover/", {"carpeta_id": folder_id}, format="json").status_code,
            403,
        )

    def test_deleting_folder_returns_conversation_to_inbox(self):
        self.client.force_authenticate(user=self.teacher)
        folder_id = self.client.post("/api/mensajes/carpetas/", {"nombre": "Seguimiento"}, format="json").json()["id"]
        self.client.post(f"/api/mensajes/{self.first.id}/mover/", {"carpeta_id": folder_id}, format="json")
        self.assertEqual(self.client.delete(f"/api/mensajes/carpetas/{folder_id}").status_code, 204)
        self.assertFalse(CarpetaMensajes.objects.filter(pk=folder_id).exists())
        self.assertEqual(
            {item["carpeta_id"] for item in self.client.get("/api/mensajes/recibidos/").json()},
            {None},
        )
