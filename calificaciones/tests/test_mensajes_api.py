from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import FieldDoesNotExist
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from calificaciones.models import Alumno, Mensaje, Notificacion, School, SchoolCourse
from calificaciones.models_preceptores import PreceptorCurso, ProfesorCurso


def _make_user(username: str, *, is_superuser: bool = False, is_staff: bool | None = None):
    User = get_user_model()
    return User.objects.create_user(
        username=username,
        password="test1234",
        is_superuser=is_superuser,
        is_staff=is_superuser if is_staff is None else is_staff,
    )


def _mensaje_has_field(name: str) -> bool:
    try:
        Mensaje._meta.get_field(name)
        return True
    except FieldDoesNotExist:
        return False


def _add_user_to_group(user, group_name: str):
    group, _ = Group.objects.get_or_create(name=group_name)
    user.groups.add(group)


@override_settings(SECURE_SSL_REDIRECT=False)
class MensajesSchoolScopingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = _make_user("admin_mensajes_school", is_superuser=True)
        self.sender = _make_user("sender_mensajes_school")
        self.school_a = School.objects.create(name="Colegio Msg Norte", slug="colegio-msg-norte")
        self.school_b = School.objects.create(name="Colegio Msg Sur", slug="colegio-msg-sur")
        self.school_course_a = SchoolCourse.objects.create(school=self.school_a, code="1A", name="1A Norte", sort_order=1)
        self.school_course_b = SchoolCourse.objects.create(school=self.school_b, code="1A", name="1A Sur", sort_order=1)
        self.msg_a = Mensaje.objects.create(
            school=self.school_a,
            remitente=self.sender,
            destinatario=self.admin,
            curso="1A",
            asunto="Mensaje Norte",
            contenido="Contenido norte",
        )
        self.msg_b = Mensaje.objects.create(
            school=self.school_b,
            remitente=self.sender,
            destinatario=self.admin,
            curso="1A",
            asunto="Mensaje Sur",
            contenido="Contenido sur",
        )
        self.client.force_authenticate(user=self.admin)

    def test_recibidos_filtra_por_school(self):
        res = self.client.get(
            "/api/mensajes/recibidos/",
            {"school": self.school_a.slug},
        )

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual([item["id"] for item in data], [self.msg_a.id])
        self.assertEqual(data[0]["school_course_name"], "1A Norte")
        self.assertNotIn("curso", data[0])
        self.assertNotIn("curso_asociado", data[0])
        self.assertEqual(self.msg_a.school_course_id, self.school_course_a.id)
        self.assertEqual(self.msg_b.school_course_id, self.school_course_b.id)


@override_settings(SECURE_SSL_REDIRECT=False)
class MensajesPadreInboxAlumnoTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.padre = _make_user("padre_inbox_alumno")
        self.otro_padre = _make_user("otro_padre_inbox_alumno")
        self.remitente = _make_user("remitente_inbox_alumno")
        _add_user_to_group(self.padre, "Padres")
        _add_user_to_group(self.otro_padre, "Padres")
        self.school = School.objects.create(name="Colegio Inbox Alumno", slug="colegio-inbox-alumno")
        self.course_a = SchoolCourse.objects.create(school=self.school, code="1A", name="1A", sort_order=1)
        self.course_b = SchoolCourse.objects.create(school=self.school, code="2A", name="2A", sort_order=2)
        self.hijo_a = Alumno.objects.create(
            school=self.school,
            school_course=self.course_a,
            nombre="Ana",
            apellido="Padre",
            id_alumno="HIJOA",
            curso="1A",
            padre=self.padre,
        )
        self.hijo_b = Alumno.objects.create(
            school=self.school,
            school_course=self.course_b,
            nombre="Beto",
            apellido="Padre",
            id_alumno="HIJOB",
            curso="2A",
            padre=self.padre,
        )
        self.msg_a = Mensaje.objects.create(
            school=self.school,
            school_course=self.course_a,
            alumno=self.hijo_a,
            remitente=self.remitente,
            destinatario=self.padre,
            curso="1A",
            asunto="Mensaje hijo A",
            contenido="Contenido hijo A",
        )
        self.msg_b = Mensaje.objects.create(
            school=self.school,
            school_course=self.course_b,
            alumno=self.hijo_b,
            remitente=self.remitente,
            destinatario=self.padre,
            curso="2A",
            asunto="Mensaje hijo B",
            contenido="Contenido hijo B",
        )

    def test_padre_filtra_recibidos_por_hijo(self):
        self.client.force_authenticate(user=self.padre)

        res = self.client.get("/api/mensajes/recibidos/", {"alumno_id": self.hijo_a.id})

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual([item["id"] for item in data], [self.msg_a.id])
        self.assertEqual(data[0]["alumno_id"], self.hijo_a.id)
        self.assertEqual(data[0]["alumno_nombre"], "Padre Ana")

    def test_padre_no_puede_filtrar_hijo_ajeno(self):
        self.client.force_authenticate(user=self.otro_padre)

        res = self.client.get("/api/mensajes/recibidos/", {"alumno_id": self.hijo_a.id})

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No autorizado para ese alumno.")


@override_settings(SECURE_SSL_REDIRECT=False)
class MensajesEliminarTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.destinatario = _make_user("destinatario_mensaje_delete")
        self.remitente = _make_user("remitente_mensaje_delete")
        self.staff_user = _make_user("staff_mensaje_delete", is_staff=True)
        self.superuser = _make_user("super_mensaje_delete", is_superuser=True)
        self.school = School.objects.get(slug="escuela-tecnova")
        self.school_course, _ = SchoolCourse.objects.get_or_create(
            school=self.school,
            code="1A",
            defaults={
                "name": "1A Delete",
                "sort_order": 1,
            },
        )
        self.mensaje = Mensaje.objects.create(
            school=self.school,
            remitente=self.remitente,
            destinatario=self.destinatario,
            curso="1A",
            asunto="Eliminar",
            contenido="Mensaje a eliminar",
        )

    def test_destinatario_puede_eliminar_su_mensaje(self):
        self.client.force_authenticate(user=self.destinatario)

        res = self.client.delete(f"/api/mensajes/{self.mensaje.id}/eliminar/")

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertNotIn("ok", body)
        self.assertEqual(body["id"], self.mensaje.id)
        self.assertFalse(Mensaje.objects.filter(id=self.mensaje.id).exists())

    def test_staff_no_superuser_no_puede_eliminar_mensaje_ajeno(self):
        self.client.force_authenticate(user=self.staff_user)

        res = self.client.delete(f"/api/mensajes/{self.mensaje.id}/eliminar/")

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No autorizado.")
        self.assertTrue(Mensaje.objects.filter(id=self.mensaje.id).exists())

    def test_superuser_puede_eliminar_mensaje_ajeno(self):
        self.client.force_authenticate(user=self.superuser)

        res = self.client.delete(f"/api/mensajes/{self.mensaje.id}/eliminar/")

        self.assertEqual(res.status_code, 200)
        self.assertFalse(Mensaje.objects.filter(id=self.mensaje.id).exists())

    def test_padre_no_puede_eliminar_mensaje_no_leido(self):
        _add_user_to_group(self.destinatario, "Padres")
        self.client.force_authenticate(user=self.destinatario)

        res = self.client.delete(f"/api/mensajes/{self.mensaje.id}/eliminar/")

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No podes eliminar mensajes no leidos.")
        self.assertTrue(Mensaje.objects.filter(id=self.mensaje.id).exists())

    def test_padre_puede_eliminar_mensaje_leido(self):
        _add_user_to_group(self.destinatario, "Padres")
        if _mensaje_has_field("leido"):
            self.mensaje.leido = True
        if _mensaje_has_field("leido_en"):
            from django.utils import timezone
            self.mensaje.leido_en = timezone.now()
        update_fields = []
        if _mensaje_has_field("leido"):
            update_fields.append("leido")
        if _mensaje_has_field("leido_en"):
            update_fields.append("leido_en")
        if update_fields:
            self.mensaje.save(update_fields=update_fields)

        self.client.force_authenticate(user=self.destinatario)
        res = self.client.delete(f"/api/mensajes/{self.mensaje.id}/eliminar/")

        self.assertEqual(res.status_code, 200)
        self.assertFalse(Mensaje.objects.filter(id=self.mensaje.id).exists())


@override_settings(SECURE_SSL_REDIRECT=False)
class MensajesConversacionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.remitente = _make_user("remitente_mensaje_conv")
        self.destinatario = _make_user("destinatario_mensaje_conv")
        self.tercero = _make_user("tercero_mensaje_conv")
        self.school = School.objects.get(slug="escuela-tecnova")
        self.school_course, _ = SchoolCourse.objects.get_or_create(
            school=self.school,
            code="1A",
            defaults={
                "name": "1A Conversacion",
                "sort_order": 1,
            },
        )
        self.msg_1 = Mensaje.objects.create(
            school=self.school,
            remitente=self.remitente,
            destinatario=self.destinatario,
            curso="1A",
            asunto="Primer mensaje",
            contenido="Hola",
        )
        self.msg_2 = Mensaje.objects.create(
            school=self.school,
            remitente=self.destinatario,
            destinatario=self.remitente,
            curso="1A",
            asunto="Respuesta",
            contenido="Hola de vuelta",
        )
        Mensaje.objects.create(
            school=self.school,
            remitente=self.tercero,
            destinatario=self.destinatario,
            curso="1A",
            asunto="Ajeno",
            contenido="No deberia aparecer",
        )

    def test_conversacion_por_mensaje_devuelve_solo_la_conversacion(self):
        self.client.force_authenticate(user=self.destinatario)

        res = self.client.get(f"/api/mensajes/conversacion/{self.msg_1.id}/")

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual([item["id"] for item in body["mensajes"]], [self.msg_1.id, self.msg_2.id])
        self.assertEqual(body["thread_id"], str(self.msg_1.id))
        self.assertFalse(body["has_more"])
        self.assertIn(body["mensajes"][0]["school_course_name"], {self.school_course.name, self.school_course.code})

    def test_conversacion_por_mensaje_rechaza_usuario_ajeno(self):
        self.client.force_authenticate(user=self.tercero)

        res = self.client.get(f"/api/mensajes/conversacion/{self.msg_1.id}/")

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No autorizado.")

    def test_marcar_leido_guarda_fecha_de_lectura(self):
        self.client.force_authenticate(user=self.destinatario)

        res = self.client.post(f"/api/mensajes/{self.msg_1.id}/marcar_leido/")

        self.assertEqual(res.status_code, 204)
        self.msg_1.refresh_from_db()
        if _mensaje_has_field("leido"):
            self.assertTrue(self.msg_1.leido)
        if _mensaje_has_field("leido_en"):
            self.assertIsNotNone(self.msg_1.leido_en)


@override_settings(SECURE_SSL_REDIRECT=False)
class MensajesPermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff_sin_rol = _make_user("staff_mensajes_perm", is_staff=True)
        self.profesor_sin_asignacion = _make_user("profesor_sin_asignacion_mensajes")
        _add_user_to_group(self.profesor_sin_asignacion, "Profesores")
        self.padre = _make_user("padre_mensajes_perm")
        self.default_school = School.objects.get(slug="escuela-tecnova")
        self.default_school_course, _ = SchoolCourse.objects.get_or_create(
            school=self.default_school,
            code="1A",
            defaults={
                "name": "1A Default",
                "sort_order": 1,
            },
        )
        self.alumno = Alumno.objects.create(
            school=self.default_school,
            nombre="Nadia",
            apellido="Mensajes",
            id_alumno="LEGMSGDEF01",
            curso="1A",
            padre=self.padre,
        )

    def test_staff_sin_rol_no_puede_enviar_mensaje_individual(self):
        self.client.force_authenticate(user=self.staff_sin_rol)

        res = self.client.post(
            "/api/mensajes/enviar/",
            {
                "alumno_id": self.alumno.id,
                "asunto": "Aviso restringido",
                "contenido": "No deberia enviarse",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No autorizado para ese alumno.")
        self.assertEqual(Mensaje.objects.count(), 0)

    def test_staff_sin_rol_no_puede_enviar_mensaje_grupal(self):
        self.client.force_authenticate(user=self.staff_sin_rol)

        res = self.client.post(
            "/api/mensajes/enviar_grupal/",
            {
                "school_course_id": self.default_school_course.id,
                "asunto": "Aviso restringido",
                "contenido": "No deberia enviarse",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No autorizado para ese curso.")
        self.assertEqual(Mensaje.objects.count(), 0)

    def test_profesor_sin_asignacion_no_puede_enviar_mensaje_individual(self):
        self.client.force_authenticate(user=self.profesor_sin_asignacion)

        res = self.client.post(
            "/api/mensajes/enviar/",
            {
                "alumno_id": self.alumno.id,
                "asunto": "Aviso profesor restringido",
                "contenido": "No deberia enviarse",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No autorizado para ese alumno.")
        self.assertEqual(Mensaje.objects.count(), 0)

    def test_profesor_sin_asignacion_no_puede_enviar_mensaje_grupal(self):
        self.client.force_authenticate(user=self.profesor_sin_asignacion)

        res = self.client.post(
            "/api/mensajes/enviar_grupal/",
            {
                "school_course_id": self.default_school_course.id,
                "asunto": "Aviso profesor restringido",
                "contenido": "No deberia enviarse",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No autorizado para ese curso.")
        self.assertEqual(Mensaje.objects.count(), 0)


@override_settings(SECURE_SSL_REDIRECT=False)
class MensajesAlumnoSchoolScopingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.alumno_user = _make_user("alumno_mensajes_school")
        self.profesor_a = _make_user("profesor_mensajes_a")
        self.profesor_b = _make_user("profesor_mensajes_b")
        self.preceptor_a = _make_user("preceptor_mensajes_a")
        self.school_a = School.objects.create(name="Colegio Msg Alumno Norte", slug="colegio-msg-alumno-norte")
        self.school_b = School.objects.create(name="Colegio Msg Alumno Sur", slug="colegio-msg-alumno-sur")

        for user, group_name in (
            (self.profesor_a, "Profesores"),
            (self.profesor_b, "Profesores"),
            (self.preceptor_a, "Preceptores"),
        ):
            group, _ = Group.objects.get_or_create(name=group_name)
            user.groups.add(group)

        self.school_course_a = SchoolCourse.objects.create(school=self.school_a, code="1A", name="1A Norte", sort_order=1)
        self.school_course_b = SchoolCourse.objects.create(school=self.school_b, code="1A", name="1A Sur", sort_order=1)
        self.school_course_a_2 = SchoolCourse.objects.create(
            school=self.school_a,
            code="2A",
            name="2A Norte",
            sort_order=2,
        )
        Alumno.objects.create(
            school=self.school_a,
            nombre="Alicia",
            apellido="Mensajes",
            id_alumno="LEGMSG01",
            curso="1A",
            usuario=self.alumno_user,
        )
        self.alumno_otro_curso = Alumno.objects.create(
            school=self.school_a,
            nombre="Belen",
            apellido="Mensajes",
            id_alumno="LEGMSG05",
            curso="2A",
        )
        ProfesorCurso.objects.create(school=self.school_a, profesor=self.profesor_a, curso="1A")
        ProfesorCurso.objects.create(school=self.school_b, profesor=self.profesor_b, curso="1A")
        PreceptorCurso.objects.create(school=self.school_a, preceptor=self.preceptor_a, curso="1A")
        self.client.force_authenticate(user=self.alumno_user)

    def test_destinatarios_docentes_filtra_por_school_activo(self):
        res = self.client.get("/api/mensajes/destinatarios_docentes/")

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertNotIn("curso", data)
        self.assertEqual(data["school_course_id"], self.school_course_a.id)
        self.assertEqual(data["school_course_name"], "1A Norte")
        ids = {item["id"] for item in data["results"]}
        self.assertEqual(ids, {self.profesor_a.id, self.preceptor_a.id})

    def test_destinatarios_docentes_acepta_school_course_id(self):
        res = self.client.get(
            "/api/mensajes/destinatarios_docentes/",
            {"school_course_id": self.school_course_a.id},
        )

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["school_course_id"], self.school_course_a.id)
        self.assertEqual(data["school_course_name"], "1A Norte")
        ids = {item["id"] for item in data["results"]}
        self.assertEqual(ids, {self.profesor_a.id, self.preceptor_a.id})

    def test_destinatarios_docentes_rechaza_curso_legacy(self):
        res = self.client.get(
            "/api/mensajes/destinatarios_docentes/",
            {"curso": "1A"},
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            res.json()["detail"],
            "El parámetro 'curso' está deprecado en este endpoint. Usa school_course_id.",
        )

    def test_alumno_enviar_rechaza_destinatario_de_otro_school(self):
        res = self.client.post(
            "/api/mensajes/alumno/enviar/",
            {
                "receptor_id": self.profesor_b.id,
                "asunto": "Consulta",
                "contenido": "Hola",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(Mensaje.objects.count(), 0)

    def test_alumno_enviar_asigna_school_a_mensaje_y_notificacion(self):
        res = self.client.post(
            "/api/mensajes/alumno/enviar/",
            {
                "receptor_id": self.profesor_a.id,
                "asunto": "Consulta",
                "contenido": "Hola profe",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertNotIn("ok", body)
        self.assertNotIn("curso", body)
        self.assertNotIn("curso_asociado", body)
        self.assertEqual(body["school_course_id"], self.school_course_a.id)
        self.assertEqual(body["school_course_name"], "1A Norte")
        mensaje = Mensaje.objects.get()
        notificacion = Notificacion.objects.get()
        self.assertEqual(mensaje.school_id, self.school_a.id)
        self.assertEqual(mensaje.school_course_id, self.school_course_a.id)
        self.assertEqual(notificacion.school_id, self.school_a.id)
        self.assertEqual(notificacion.meta["school_course_id"], self.school_course_a.id)
        self.assertEqual(notificacion.meta["school_course_name"], "1A Norte")
        self.assertNotIn("curso", notificacion.meta)

    def test_alumno_enviar_acepta_school_course_id_sin_curso(self):
        res = self.client.post(
            "/api/mensajes/alumno/enviar/",
            {
                "receptor_id": self.profesor_a.id,
                "asunto": "Consulta por id",
                "contenido": "Hola profe desde id",
                "school_course_id": self.school_course_a.id,
            },
            format="json",
        )

        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertNotIn("ok", body)
        self.assertEqual(body["school_course_id"], self.school_course_a.id)
        self.assertEqual(body["school_course_name"], "1A Norte")
        mensaje = Mensaje.objects.get(asunto="Consulta por id")
        self.assertEqual(mensaje.curso, "1A")
        self.assertEqual(mensaje.school_course_id, self.school_course_a.id)

    def test_alumno_enviar_rechaza_curso_legacy(self):
        res = self.client.post(
            "/api/mensajes/alumno/enviar/",
            {
                "receptor_id": self.profesor_a.id,
                "asunto": "Consulta legacy",
                "contenido": "Hola profe desde curso legacy",
                "curso": "1A",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            res.json()["detail"],
            "El par\u00e1metro 'curso' est\u00e1 deprecado en este endpoint. Usa school_course_id.",
        )

    def test_profesor_puede_enviar_mensaje_individual_sin_wrapper_ok(self):
        self.client.force_authenticate(user=self.profesor_a)

        res = self.client.post(
            "/api/mensajes/enviar/",
            {
                "alumno_id": Alumno.objects.get(id_alumno="LEGMSG01").id,
                "asunto": "Aviso individual",
                "contenido": "Mensaje al alumno",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertNotIn("ok", body)
        self.assertEqual(body["mensajes_creados"], 1)
        self.assertEqual(body["receptor"], self.alumno_user.id)
        self.assertEqual(body["receptores"], [self.alumno_user.id])
        mensaje = Mensaje.objects.get(asunto="Aviso individual")
        self.assertEqual(mensaje.school_id, self.school_a.id)
        self.assertEqual(mensaje.school_course_id, self.school_course_a.id)

    def test_profesor_rechaza_curso_legacy_en_mensaje_individual(self):
        self.client.force_authenticate(user=self.profesor_a)

        res = self.client.post(
            "/api/mensajes/enviar/",
            {
                "alumno_id": Alumno.objects.get(id_alumno="LEGMSG01").id,
                "asunto": "Aviso legacy",
                "contenido": "No deberia aceptarse",
                "curso": "1A",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            res.json()["detail"],
            "El parámetro 'curso' está deprecado en este endpoint. Usa school_course_id.",
        )

    def test_enviar_mensaje_grupal_asigna_school_course_a_todos(self):
        padre_uno = _make_user("padre_grupal_msg_1")
        padre_dos = _make_user("padre_grupal_msg_2")
        Alumno.objects.create(
            school=self.school_a,
            nombre="Bruno",
            apellido="Mensajes",
            id_alumno="LEGMSG02",
            curso="1A",
            padre=padre_uno,
        )
        Alumno.objects.create(
            school=self.school_a,
            nombre="Carla",
            apellido="Mensajes",
            id_alumno="LEGMSG03",
            curso="1A",
            padre=padre_dos,
        )
        self.client.force_authenticate(user=self.profesor_a)

        res = self.client.post(
            "/api/mensajes/enviar_grupal/",
            {
                "school_course_id": self.school_course_a.id,
                "asunto": "Aviso general",
                "contenido": "Hola curso",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertNotIn("ok", body)
        self.assertEqual(body["creados"], 3)
        self.assertEqual(body["mensajes_creados"], 3)
        course_ids = list(Mensaje.objects.order_by("id").values_list("school_course_id", flat=True))
        self.assertEqual(len(course_ids), 3)
        self.assertEqual(set(course_ids), {self.school_course_a.id})
        notif_names = set(Notificacion.objects.order_by("id").values_list("meta__school_course_name", flat=True))
        self.assertEqual(notif_names, {"1A Norte"})

    def test_enviar_mensaje_grupal_rechaza_curso_legacy(self):
        self.client.force_authenticate(user=self.profesor_a)

        res = self.client.post(
            "/api/mensajes/enviar_grupal/",
            {
                "curso": "1A",
                "asunto": "Aviso legacy",
                "contenido": "No deberia aceptarse",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            res.json()["detail"],
            "El par\u00e1metro 'curso' est\u00e1 deprecado en este endpoint. Usa school_course_id.",
        )

    def test_enviar_mensaje_grupal_acepta_school_course_id_sin_curso(self):
        padre = _make_user("padre_grupal_msg_3")
        Alumno.objects.create(
            school=self.school_a,
            nombre="Dario",
            apellido="Mensajes",
            id_alumno="LEGMSG04",
            curso="1A",
            padre=padre,
        )
        self.client.force_authenticate(user=self.profesor_a)

        res = self.client.post(
            "/api/mensajes/enviar_grupal/",
            {
                "school_course_id": self.school_course_a.id,
                "asunto": "Aviso por id",
                "contenido": "Hola desde school_course_id",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertNotIn("ok", body)
        self.assertEqual(body["creados"], 2)
        self.assertEqual(body["mensajes_creados"], 2)
        mensajes = list(Mensaje.objects.filter(asunto="Aviso por id").values_list("curso", "school_course_id"))
        self.assertEqual(mensajes, [("1A", self.school_course_a.id), ("1A", self.school_course_a.id)])
        notif_names = set(
            Notificacion.objects.filter(meta__mensaje_id__isnull=False).values_list("meta__school_course_name", flat=True)
        )
        self.assertEqual(notif_names, {"1A Norte"})
        self.assertFalse(
            Notificacion.objects.filter(meta__mensaje_id__isnull=False, meta__curso__isnull=False).exists()
        )

    def test_profesor_no_puede_enviar_mensaje_individual_a_alumno_fuera_de_su_curso(self):
        self.client.force_authenticate(user=self.profesor_a)

        res = self.client.post(
            "/api/mensajes/enviar/",
            {
                "alumno_id": self.alumno_otro_curso.id,
                "asunto": "Aviso restringido",
                "contenido": "No deberia enviarse",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No autorizado para ese alumno.")
        self.assertEqual(Mensaje.objects.count(), 0)

    def test_profesor_no_puede_enviar_grupal_a_otro_curso_del_mismo_colegio(self):
        padre = _make_user("padre_grupal_msg_4")
        Alumno.objects.create(
            school=self.school_a,
            nombre="Emma",
            apellido="Mensajes",
            id_alumno="LEGMSG06",
            curso="2A",
            padre=padre,
        )
        self.client.force_authenticate(user=self.profesor_a)

        res = self.client.post(
            "/api/mensajes/enviar_grupal/",
            {
                "school_course_id": self.school_course_a_2.id,
                "asunto": "Aviso restringido",
                "contenido": "No deberia enviarse",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No autorizado para ese curso.")
        self.assertEqual(Mensaje.objects.count(), 0)

    def test_responder_mensaje_preserva_alumno_y_school_course_del_original(self):
        kwargs = {
            "school": self.school_a,
            "school_course": self.school_course_a,
            "remitente": self.profesor_a,
            "destinatario": self.alumno_user,
            "curso": "1A",
            "asunto": "Consulta inicial",
            "contenido": "Mensaje original",
        }
        if _mensaje_has_field("alumno"):
            kwargs["alumno"] = Alumno.objects.get(id_alumno="LEGMSG01")

        original = Mensaje.objects.create(**kwargs)
        self.client.force_authenticate(user=self.alumno_user)

        res = self.client.post(
            "/api/mensajes/responder/",
            {
                "mensaje_id": original.id,
                "contenido": "Respuesta del alumno",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertNotIn("ok", body)
        self.assertEqual(body["id"], Mensaje.objects.exclude(id=original.id).get().id)
        reply = Mensaje.objects.exclude(id=original.id).get()
        notif = Notificacion.objects.filter(destinatario=self.profesor_a, tipo="mensaje").latest("id")
        self.assertEqual(reply.school_id, self.school_a.id)
        self.assertEqual(reply.school_course_id, self.school_course_a.id)
        self.assertEqual(reply.curso, "1A")
        self.assertEqual(notif.meta["school_course_id"], self.school_course_a.id)
        self.assertEqual(notif.meta["school_course_name"], "1A Norte")
        if _mensaje_has_field("alumno"):
            self.assertEqual(reply.alumno_id, original.alumno_id)
            self.assertEqual(notif.meta["alumno_id"], original.alumno_id)
