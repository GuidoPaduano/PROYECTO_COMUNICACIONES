from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase, override_settings

from calificaciones.models import Alumno, Asistencia, Evento, Mensaje, Notificacion, School, SchoolCourse
from calificaciones.models_preceptores import PreceptorCurso, ProfesorCurso


def _make_user(username: str, groups: list[str] | None = None, *, is_superuser: bool = False):
    User = get_user_model()
    user = User.objects.create_user(
        username=username,
        password="test1234",
        is_superuser=is_superuser,
        is_staff=is_superuser,
    )
    for group_name in groups or []:
        group, _ = Group.objects.get_or_create(name=group_name)
        user.groups.add(group)
    return user


@override_settings(SECURE_SSL_REDIRECT=False)
class LegacyHtmlSchoolCourseTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.profesor = _make_user("profesor_html_school_course", ["Profesores"])
        self.preceptor = _make_user("preceptor_html_school_course", ["Preceptores"])
        self.admin = _make_user("admin_html_school_course", is_superuser=True)
        self.padre_a = _make_user("padre_html_a", ["Padres"])
        self.padre_b = _make_user("padre_html_b", ["Padres"])
        self.school = School.objects.create(name="Colegio HTML Norte", slug="colegio-html-norte")
        self.course_1a = SchoolCourse.objects.create(school=self.school, code="1A", name="1A Norte", sort_order=1)
        self.course_2a = SchoolCourse.objects.create(school=self.school, code="2A", name="2A Norte", sort_order=2)
        ProfesorCurso.objects.create(school=self.school, profesor=self.profesor, curso="1A")
        PreceptorCurso.objects.create(school=self.school, preceptor=self.preceptor, curso="1A")
        PreceptorCurso.objects.create(school=self.school, preceptor=self.preceptor, curso="2A")
        self.alumno_a = Alumno.objects.create(
            school=self.school,
            nombre="Ana",
            apellido="HTML",
            id_alumno="HTML001",
            curso="1A",
            padre=self.padre_a,
        )
        self.alumno_b = Alumno.objects.create(
            school=self.school,
            nombre="Bruno",
            apellido="HTML",
            id_alumno="HTML002",
            curso="1A",
            padre=self.padre_b,
        )
        self.alumno_c = Alumno.objects.create(
            school=self.school,
            nombre="Carla",
            apellido="HTML",
            id_alumno="HTML003",
            curso="2A",
        )

    def test_crear_evento_html_acepta_school_course_id(self):
        self.client.force_login(self.profesor)

        res = self.client.post(
            "/eventos/crear/",
            {
                "titulo": "Acto HTML",
                "descripcion": "Evento desde form HTML",
                "fecha": "2026-03-27",
                "school_course_id": str(self.course_1a.id),
                "tipo_evento": "Acto",
            },
        )

        self.assertEqual(res.status_code, 200)
        evento = Evento.objects.get(titulo="Acto HTML")
        self.assertEqual(res.json(), {"id": evento.id})
        self.assertEqual(evento.school_id, self.school.id)
        self.assertEqual(evento.school_course_id, self.course_1a.id)
        self.assertEqual(evento.curso, "1A")

    def test_crear_evento_html_rechaza_curso_legacy(self):
        self.client.force_login(self.profesor)

        res = self.client.post(
            f"/eventos/crear/?school={self.school.slug}",
            {
                "titulo": "Acto HTML legacy",
                "descripcion": "No deberia aceptarse",
                "fecha": "2026-03-27",
                "curso": "1A",
                "tipo_evento": "Acto",
            },
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            res.json()["detail"],
            "El parámetro 'curso' está deprecado en este endpoint. Usa school_course_id.",
        )

    def test_editar_evento_html_devuelve_id_sin_wrapper_success(self):
        self.client.force_login(self.admin)
        evento = Evento.objects.create(
            school=self.school,
            school_course=self.course_1a,
            curso="1A",
            titulo="Acto HTML viejo",
            descripcion="Antes",
            fecha="2026-03-27",
            tipo_evento="Acto",
        )

        res = self.client.post(
            f"/eventos/editar/{evento.id}/?school={self.school.slug}",
            {
                "titulo": "Acto HTML editado",
                "descripcion": "Despues",
                "fecha": "2026-03-28",
                "school_course_id": str(self.course_1a.id),
                "tipo_evento": "Acto",
            },
        )

        self.assertEqual(res.status_code, 200)
        evento.refresh_from_db()
        self.assertEqual(res.json(), {"id": evento.id})
        self.assertEqual(evento.titulo, "Acto HTML editado")
        self.assertEqual(evento.school_course_id, self.course_1a.id)

    def test_enviar_mensaje_html_acepta_school_course_id_y_alumno_pk(self):
        self.client.force_login(self.profesor)

        res = self.client.post(
            "/enviar_mensaje/",
            {
                "school_course_id": str(self.course_1a.id),
                "alumno": str(self.alumno_a.id),
                "asunto": "Mensaje HTML",
                "contenido": "Contenido HTML",
            },
        )

        self.assertEqual(res.status_code, 302)
        mensaje = Mensaje.objects.get(asunto="Mensaje HTML")
        notif = Notificacion.objects.get(tipo="mensaje", destinatario=self.padre_a)
        self.assertEqual(mensaje.destinatario_id, self.padre_a.id)
        self.assertEqual(mensaje.school_id, self.school.id)
        self.assertEqual(mensaje.school_course_id, self.course_1a.id)
        self.assertEqual(mensaje.curso, "1A")
        self.assertEqual(notif.meta["school_course_id"], self.course_1a.id)
        self.assertEqual(notif.meta["school_course_name"], "1A Norte")
        self.assertNotIn("curso", notif.meta)

    def test_enviar_mensaje_html_rechaza_curso_legacy(self):
        self.client.force_login(self.profesor)

        res = self.client.post(
            f"/enviar_mensaje/?school={self.school.slug}&curso=1A",
            {
                "alumno": str(self.alumno_a.id),
                "asunto": "Mensaje HTML legacy",
                "contenido": "No deberia aceptarse",
            },
        )

        self.assertEqual(res.status_code, 400)
        self.assertContains(
            res,
            "El parámetro 'curso' está deprecado en este endpoint. Usa school_course_id.",
            status_code=400,
        )

    def test_enviar_comunicado_html_acepta_school_course_id(self):
        self.client.force_login(self.profesor)

        res = self.client.post(
            "/enviar_comunicado/",
            {
                "school_course_id": str(self.course_1a.id),
                "asunto": "Comunicado HTML",
                "contenido": "Aviso para primero",
            },
        )

        self.assertEqual(res.status_code, 302)
        mensajes = list(Mensaje.objects.filter(asunto="Comunicado HTML").order_by("id"))
        notifs = list(Notificacion.objects.filter(tipo="mensaje").order_by("id"))
        self.assertEqual(len(mensajes), 2)
        self.assertEqual({m.destinatario_id for m in mensajes}, {self.padre_a.id, self.padre_b.id})
        self.assertEqual({m.school_course_id for m in mensajes}, {self.course_1a.id})
        self.assertEqual(len(notifs), 2)
        self.assertEqual({n.meta["school_course_id"] for n in notifs}, {self.course_1a.id})
        self.assertEqual({n.meta["school_course_name"] for n in notifs}, {"1A Norte"})
        self.assertTrue(all("curso" not in n.meta for n in notifs))

    def test_enviar_comunicado_html_rechaza_curso_legacy(self):
        self.client.force_login(self.profesor)

        res = self.client.post(
            f"/enviar_comunicado/?school={self.school.slug}",
            {
                "curso": "1A",
                "asunto": "Comunicado HTML legacy",
                "contenido": "No deberia aceptarse",
            },
        )

        self.assertEqual(res.status_code, 400)
        self.assertContains(
            res,
            "El parámetro 'curso' está deprecado en este endpoint. Usa school_course_id.",
            status_code=400,
        )

    def test_enviar_comunicado_html_get_rechaza_curso_legacy(self):
        self.client.force_login(self.profesor)

        res = self.client.get(
            f"/enviar_comunicado/?school={self.school.slug}&curso=1A",
        )

        self.assertEqual(res.status_code, 400)
        self.assertContains(
            res,
            "El parámetro 'curso' está deprecado en este endpoint. Usa school_course_id.",
            status_code=400,
        )

    def test_pasar_asistencia_superuser_acepta_school_course_id(self):
        self.client.force_login(self.admin)

        res = self.client.post(
            f"/pasar_asistencia/?school={self.school.slug}&school_course_id={self.course_1a.id}",
            {
                "school_course_id": str(self.course_1a.id),
                f"asistencia_{self.alumno_a.id}": "on",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"registradas": 2})

        asistencias = list(Asistencia.objects.filter(fecha=date.today()).order_by("alumno_id"))
        notif = Notificacion.objects.get(tipo="inasistencia", destinatario=self.padre_b)
        self.assertEqual([a.alumno_id for a in asistencias], [self.alumno_a.id, self.alumno_b.id])
        self.assertTrue(all(a.school_id == self.school.id for a in asistencias))
        self.assertEqual({a.presente for a in asistencias}, {False, True})
        self.assertEqual(notif.meta["school_course_id"], self.course_1a.id)
        self.assertEqual(notif.meta["school_course_name"], "1A Norte")
        self.assertNotIn("curso", notif.meta)
        self.assertIn("1A Norte", notif.descripcion)

    def test_pasar_asistencia_superuser_rechaza_curso_legacy(self):
        self.client.force_login(self.admin)

        res = self.client.get(
            f"/pasar_asistencia/?school={self.school.slug}&curso=1A",
        )

        self.assertEqual(res.status_code, 400)
        self.assertContains(res, "El parámetro", status_code=400)
        self.assertContains(res, "school_course_id.", status_code=400)

    def test_pasar_asistencia_preceptor_acepta_school_course_id_de_curso_asignado(self):
        self.client.force_login(self.preceptor)

        res = self.client.post(
            f"/pasar_asistencia/?school={self.school.slug}&school_course_id={self.course_2a.id}",
            {
                "school_course_id": str(self.course_2a.id),
                f"asistencia_{self.alumno_c.id}": "on",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"registradas": 1})

        asistencias = list(Asistencia.objects.filter(fecha=date.today()).order_by("alumno_id"))
        self.assertEqual([a.alumno_id for a in asistencias], [self.alumno_c.id])
        self.assertEqual(asistencias[0].school_id, self.school.id)
        self.assertTrue(asistencias[0].presente)

    def test_index_preceptor_muestra_boton_de_asistencia_por_asignacion_real(self):
        self.client.force_login(self.preceptor)

        res = self.client.get("/")

        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Pasar asistencia")

    def test_agregar_nota_html_get_rechaza_curso_legacy(self):
        self.client.force_login(self.profesor)

        res = self.client.get(
            f"/agregar_nota/?school={self.school.slug}&curso=1A",
        )

        self.assertEqual(res.status_code, 400)
        self.assertContains(
            res,
            "El parámetro 'curso' está deprecado en este endpoint. Usa school_course_id.",
            status_code=400,
        )

    def test_agregar_nota_masiva_rechaza_curso_legacy(self):
        self.client.force_login(self.profesor)

        res = self.client.post(
            f"/agregar_nota_masiva/?school={self.school.slug}",
            {
                "curso": "1A",
                "alumno[]": [self.alumno_a.id_alumno],
                "materia[]": ["Matemática"],
                "tipo[]": ["Examen"],
                "calificacion[]": ["TEA"],
                "resultado[]": ["Aprobado"],
                "nota_numerica[]": ["9"],
                "cuatrimestre[]": ["1"],
                "fecha[]": ["2026-03-27"],
            },
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            res.json()["detail"],
            "El parámetro 'curso' está deprecado en este endpoint. Usa school_course_id.",
        )

    def test_agregar_nota_masiva_get_devuelve_detail_en_405(self):
        self.client.force_login(self.profesor)

        res = self.client.get("/agregar_nota_masiva/")

        self.assertEqual(res.status_code, 405)
        self.assertEqual(res.json(), {"detail": "Metodo no permitido"})
