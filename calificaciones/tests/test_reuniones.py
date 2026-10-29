from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from calificaciones.models import Alumno, InvitadoReunion, Mensaje, Notificacion, Reunion, School, SchoolCourse
from calificaciones.models_preceptores import PreceptorCurso, SchoolMembership


@override_settings(SECURE_SSL_REDIRECT=False, EMAIL_NOTIFICATIONS_ENABLED=False)
class ReunionTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Colegio Reuniones", slug="colegio-reuniones")
        self.course = SchoolCourse.objects.create(school=self.school, code="1A", name="1A")
        users = get_user_model()
        self.preceptor = users.objects.create_user(username="preceptor_reunion")
        self.family = users.objects.create_user(username="familia_reunion")
        self.teacher = users.objects.create_user(username="profesor_reunion")
        self.stranger = users.objects.create_user(username="extra_reunion")
        self.preceptor.groups.add(Group.objects.get_or_create(name="Preceptores")[0])
        self.teacher.groups.add(Group.objects.get_or_create(name="Profesores")[0])
        for user in (self.preceptor, self.family, self.teacher, self.stranger):
            SchoolMembership.objects.create(school=self.school, user=user)
        PreceptorCurso.objects.create(school=self.school, school_course=self.course, preceptor=self.preceptor, curso="1A")
        self.student = Alumno.objects.create(
            school=self.school, school_course=self.course, curso="1A", nombre="Ana",
            id_alumno="R001", padre=self.family,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.preceptor)
        self.kwargs = {"HTTP_X_SCHOOL": self.school.slug}

    def payload(self):
        return {
            "alumno_id": self.student.id,
            "inicio": (timezone.now() + timedelta(days=2)).isoformat(),
            "duracion_minutos": 30,
            "modalidad": "presencial",
            "lugar": "Secretaría",
            "motivo": "Seguimiento escolar",
            "invitados_ids": [self.teacher.id],
        }

    def create_meeting(self):
        response = self.client.post("/api/reuniones/", self.payload(), format="json", **self.kwargs)
        self.assertEqual(response.status_code, 201, response.data)
        return Reunion.objects.get(pk=response.data["id"])

    def test_invitation_is_in_family_thread_and_staff_receives_only_notification(self):
        meeting = self.create_meeting()
        self.assertEqual(meeting.familiar, self.family)
        self.assertEqual(meeting.mensaje_familia.destinatario, self.family)
        self.assertEqual(meeting.mensaje_familia.alumno, self.student)
        self.assertTrue(InvitadoReunion.objects.filter(reunion=meeting, usuario=self.teacher).exists())
        notification = Notificacion.objects.get(destinatario=self.teacher, meta__reunion_id=meeting.id)
        self.assertEqual(notification.url, f"/calendario?reunion={meeting.id}")
        self.assertFalse(Mensaje.objects.filter(destinatario=self.teacher).exists())

        self.client.force_authenticate(self.family)
        detail = self.client.get(f"/api/reuniones/{meeting.id}/", **self.kwargs)
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.data["es_familiar"])
        thread = self.client.get(f"/api/mensajes/conversacion/{meeting.mensaje_familia_id}/", **self.kwargs)
        self.assertEqual(thread.status_code, 200, thread.data)
        self.assertEqual(thread.data["mensajes"][0]["reunion"]["id"], meeting.id)

        self.client.force_authenticate(self.teacher)
        detail = self.client.get(f"/api/reuniones/{meeting.id}/", **self.kwargs)
        self.assertEqual(detail.status_code, 200)
        self.assertFalse(detail.data["es_familiar"])
        self.assertNotIn("invitados", detail.data)
        self.assertEqual(self.client.get(
            f"/api/mensajes/conversacion/{meeting.mensaje_familia_id}/", **self.kwargs
        ).status_code, 403)

        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.get(f"/api/reuniones/{meeting.id}/", **self.kwargs).status_code, 404)

    def test_family_and_staff_reply_then_reschedule_clears_confirmations(self):
        meeting = self.create_meeting()
        self.client.force_authenticate(self.family)
        family_reply = self.client.post(
            f"/api/reuniones/{meeting.id}/responder/", {"accion": "confirmar"}, format="json", **self.kwargs
        )
        self.assertEqual(family_reply.status_code, 200, family_reply.data)
        self.client.force_authenticate(self.teacher)
        staff_reply = self.client.post(
            f"/api/reuniones/{meeting.id}/responder/", {"accion": "confirmar"}, format="json", **self.kwargs
        )
        self.assertEqual(staff_reply.status_code, 200, staff_reply.data)
        self.assertEqual(self.client.post(
            f"/api/reuniones/{meeting.id}/responder/", {"accion": "solicitar_cambio"}, format="json", **self.kwargs
        ).status_code, 400)

        self.client.force_authenticate(self.preceptor)
        change = self.payload()
        change["inicio"] = (timezone.now() + timedelta(days=3)).isoformat()
        response = self.client.patch(f"/api/reuniones/{meeting.id}/", change, format="json", **self.kwargs)
        self.assertEqual(response.status_code, 200, response.data)
        meeting.refresh_from_db()
        self.assertEqual(meeting.estado, "pendiente")
        self.assertIsNone(meeting.respuesta_familiar_en)
        self.assertIsNone(meeting.invitados.get(usuario=self.teacher).confirmado_en)

        reminder = self.client.post(f"/api/reuniones/{meeting.id}/recordatorio/", {}, format="json", **self.kwargs)
        self.assertEqual(reminder.data["enviados"], 2)
        self.assertEqual(self.client.patch(
            f"/api/reuniones/{meeting.id}/", {"cancelar": True}, format="json", **self.kwargs
        ).status_code, 200)
        self.assertEqual(self.client.post(
            f"/api/reuniones/{meeting.id}/responder/", {"accion": "confirmar"}, format="json", **self.kwargs
        ).status_code, 400)

    def test_unassigned_preceptor_and_other_school_staff_are_denied(self):
        other = School.objects.create(name="Otro", slug="otro-reuniones")
        outsider = get_user_model().objects.create_user(username="outside_reunion")
        outsider.groups.add(Group.objects.get(name="Profesores"))
        SchoolMembership.objects.create(school=other, user=outsider)
        payload = self.payload()
        payload["invitados_ids"] = [outsider.id]
        response = self.client.post("/api/reuniones/", payload, format="json", **self.kwargs)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Reunion.objects.exists())

        PreceptorCurso.objects.all().delete()
        response = self.client.post("/api/reuniones/", self.payload(), format="json", **self.kwargs)
        self.assertEqual(response.status_code, 403)

    def test_family_can_request_a_new_time_and_organizer_is_notified(self):
        meeting = self.create_meeting()
        self.client.force_authenticate(self.family)
        response = self.client.post(
            f"/api/reuniones/{meeting.id}/responder/",
            {"accion": "solicitar_cambio", "nota": "Podemos reunirnos el jueves"},
            format="json", **self.kwargs,
        )
        self.assertEqual(response.status_code, 200, response.data)
        meeting.refresh_from_db()
        self.assertEqual(meeting.estado, "cambio_solicitado")
        self.assertEqual(meeting.nota_familiar, "Podemos reunirnos el jueves")
        self.assertTrue(Notificacion.objects.filter(
            destinatario=self.preceptor, meta__reunion_id=meeting.id,
            titulo="Cambio de horario solicitado",
        ).exists())

    def test_calendar_date_filter_and_invalid_student_id(self):
        meeting = self.create_meeting()
        day = timezone.localtime(meeting.inicio).date()
        response = self.client.get("/api/reuniones/", {"desde": day.isoformat(), "hasta": (day + timedelta(days=1)).isoformat()}, **self.kwargs)
        self.assertEqual([item["id"] for item in response.data], [meeting.id])
        response = self.client.get("/api/reuniones/", {"desde": (day + timedelta(days=1)).isoformat()}, **self.kwargs)
        self.assertEqual(response.data, [])
        self.assertEqual(self.client.get("/api/reuniones/opciones/", {"alumno_id": "invalid"}, **self.kwargs).status_code, 403)

    def test_physical_meeting_needs_no_place_but_virtual_meeting_needs_link(self):
        payload = self.payload()
        payload["lugar"] = ""
        response = self.client.post("/api/reuniones/", payload, format="json", **self.kwargs)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Reunion.objects.get(pk=response.data["id"]).lugar, "")

        payload["modalidad"] = "virtual"
        response = self.client.post("/api/reuniones/", payload, format="json", **self.kwargs)
        self.assertEqual(response.status_code, 400)
