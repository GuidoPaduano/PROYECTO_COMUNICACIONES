from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from calificaciones.models import Alumno, Evento, Notificacion, School, SchoolCourse
from calificaciones.models_preceptores import PreceptorCurso, ProfesorCurso
from calificaciones.serializers import EventoSerializer


def _make_user(username: str, groups: list[str], *, is_staff: bool = False):
    User = get_user_model()
    user = User.objects.create_user(username=username, password="test1234", is_staff=is_staff)
    for name in groups:
        group, _ = Group.objects.get_or_create(name=name)
        user.groups.add(group)
    return user


@override_settings(SECURE_SSL_REDIRECT=False)
class EventosSchoolScopingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.profesor = _make_user("profesor_eventos_school", ["Profesores"])
        self.profesor_sin_asignacion = _make_user("profesor_eventos_sin_asignacion", ["Profesores"])
        self.profesor_otro_curso = _make_user("profesor_eventos_otro_curso", ["Profesores"])
        self.preceptor = _make_user("preceptor_eventos_school", ["Preceptores"])
        self.preceptor_sin_asignacion = _make_user("preceptor_eventos_sin_asignacion", ["Preceptores"])
        self.staff_sin_rol = _make_user("staff_eventos_sin_rol", [], is_staff=True)
        self.padre_a = _make_user("padre_eventos_a", ["Padres"])
        self.padre_b = _make_user("padre_eventos_b", ["Padres"])
        self.school_a = School.objects.create(name="Colegio Eventos Norte", slug="colegio-eventos-norte")
        self.school_b = School.objects.create(name="Colegio Eventos Sur", slug="colegio-eventos-sur")
        self.school_course_a = SchoolCourse.objects.create(school=self.school_a, code="1A", name="1A Norte", sort_order=1)
        self.school_course_a_2 = SchoolCourse.objects.create(school=self.school_a, code="2A", name="2A Norte", sort_order=2)
        self.school_course_b = SchoolCourse.objects.create(school=self.school_b, code="1A", name="1A Sur", sort_order=1)
        ProfesorCurso.objects.create(
            school=self.school_a,
            profesor=self.profesor,
            curso="1A",
        )
        ProfesorCurso.objects.create(
            school=self.school_a,
            profesor=self.profesor_otro_curso,
            curso="2A",
        )
        PreceptorCurso.objects.create(
            school=self.school_a,
            preceptor=self.preceptor,
            curso="1A",
        )
        Alumno.objects.create(
            school=self.school_a,
            nombre="Luz",
            apellido="Diaz",
            id_alumno="EVA001",
            curso="1A",
            padre=self.padre_a,
        )
        Alumno.objects.create(
            school=self.school_b,
            nombre="Gael",
            apellido="Ruiz",
            id_alumno="EVB001",
            curso="1A",
            padre=self.padre_b,
        )

    def test_profesor_solo_lista_eventos_de_su_school(self):
        evento_a = Evento.objects.create(
            school=self.school_a,
            school_course=self.school_course_a,
            titulo="Acto Norte",
            descripcion="Evento Norte",
            curso="1A",
            fecha="2026-03-20",
            tipo_evento="Acto",
        )
        Evento.objects.create(
            school=self.school_b,
            school_course=self.school_course_b,
            titulo="Acto Sur",
            descripcion="Evento Sur",
            curso="1A",
            fecha="2026-03-20",
            tipo_evento="Acto",
        )
        self.client.force_authenticate(user=self.profesor)

        res = self.client.get("/api/eventos/", {"school_course_id": self.school_course_a.id})

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual([item["id"] for item in body], [str(evento_a.id)])
        self.assertEqual(body[0]["school_course_name"], "1A Norte")
        self.assertEqual(body[0]["extendedProps"]["school_course_name"], "1A Norte")
        self.assertNotIn("curso", body[0]["extendedProps"])
        self.assertNotIn("curso_nombre", body[0]["extendedProps"])

    def test_profesor_puede_filtrar_eventos_por_school_course_id(self):
        evento_a = Evento.objects.create(
            school=self.school_a,
            school_course=self.school_course_a,
            titulo="Acto Norte por id",
            descripcion="Evento Norte",
            curso="1A",
            fecha="2026-03-25",
            tipo_evento="Acto",
        )
        Evento.objects.create(
            school=self.school_b,
            school_course=self.school_course_b,
            titulo="Acto Sur por id",
            descripcion="Evento Sur",
            curso="1A",
            fecha="2026-03-25",
            tipo_evento="Acto",
        )
        self.client.force_authenticate(user=self.profesor)

        res = self.client.get("/api/eventos/", {"school_course_id": self.school_course_a.id})

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual([item["id"] for item in body], [str(evento_a.id)])
        self.assertEqual(body[0]["school_course_id"], self.school_course_a.id)
        self.assertEqual(body[0]["school_course_name"], "1A Norte")

    def test_profesor_rechaza_curso_legacy_en_listado(self):
        self.client.force_authenticate(user=self.profesor)

        res = self.client.get("/api/eventos/", {"curso": "1A"})

        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            res.json()["detail"],
            "El par\u00e1metro 'curso' est\u00e1 deprecado en este endpoint. Usa school_course_id.",
        )

    def test_profesor_puede_listar_eventos_con_curso_all(self):
        evento_asignado = Evento.objects.create(
            school=self.school_a,
            school_course=self.school_course_a,
            titulo="Acto Norte ALL",
            descripcion="Evento permitido",
            curso="1A",
            fecha="2026-03-26",
            tipo_evento="Acto",
        )
        Evento.objects.create(
            school=self.school_a,
            school_course=self.school_course_a_2,
            titulo="Acto 2A ALL",
            descripcion="Evento no asignado",
            curso="2A",
            fecha="2026-03-26",
            tipo_evento="Acto",
        )
        Evento.objects.create(
            school=self.school_b,
            school_course=self.school_course_b,
            titulo="Acto Sur ALL",
            descripcion="Evento otro colegio",
            curso="1A",
            fecha="2026-03-26",
            tipo_evento="Acto",
        )
        self.client.force_authenticate(user=self.profesor)

        res = self.client.get("/api/eventos/", {"curso": "ALL"})

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual([item["id"] for item in body], [str(evento_asignado.id)])
        self.assertEqual(body[0]["school_course_id"], self.school_course_a.id)

    def test_profesor_sin_asignacion_no_puede_listar_eventos(self):
        Evento.objects.create(
            school=self.school_a,
            school_course=self.school_course_a,
            titulo="Acto Norte abierto",
            descripcion="Evento Norte",
            curso="1A",
            fecha="2026-03-29",
            tipo_evento="Acto",
        )
        self.client.force_authenticate(user=self.profesor_sin_asignacion)

        res = self.client.get("/api/eventos/", {"school": self.school_a.slug})

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No tenes cursos asignados para ver eventos.")

    def test_profesor_no_puede_crear_evento_en_otro_curso_del_mismo_colegio(self):
        self.client.force_authenticate(user=self.profesor_otro_curso)

        res = self.client.post(
            "/api/eventos/",
            {
                "titulo": "Reunion Norte bloqueada",
                "fecha": "2026-03-30",
                "descripcion": "Sin asignacion",
                "school_course_id": self.school_course_a.id,
                "tipo_evento": "Acto",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No tenés permiso para crear eventos en este curso.")
        self.assertFalse(Evento.objects.filter(titulo="Reunion Norte bloqueada").exists())

    def test_staff_sin_rol_no_puede_crear_evento(self):
        self.client.force_authenticate(user=self.staff_sin_rol)

        res = self.client.post(
            "/api/eventos/",
            {
                "titulo": "Evento staff invalido",
                "fecha": "2026-03-30",
                "descripcion": "Sin rol",
                "school_course_id": self.school_course_a.id,
                "tipo_evento": "Acto",
            },
            format="json",
            HTTP_X_SCHOOL=self.school_a.slug,
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No autorizado.")
        self.assertFalse(Evento.objects.filter(titulo="Evento staff invalido").exists())

    def test_crear_evento_asigna_school_y_notifica_solo_destinatarios_del_school(self):
        self.client.force_authenticate(user=self.profesor)

        res = self.client.post(
            "/api/eventos/",
            {
                "titulo": "Reunion Norte",
                "fecha": "2026-03-21",
                "descripcion": "Reunion de curso",
                "school_course_id": self.school_course_a.id,
                "tipo_evento": "Acto",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 201)
        evento = Evento.objects.get(titulo="Reunion Norte")
        self.assertEqual(evento.school_id, self.school_a.id)
        self.assertEqual(evento.school_course_id, self.school_course_a.id)
        self.assertEqual(evento.creado_por_id, self.profesor.id)
        self.assertEqual(res.json()["creado_por"], self.profesor.username)

        notif = Notificacion.objects.filter(tipo="evento", destinatario=self.padre_a).latest("id")
        self.assertEqual(notif.meta["school_course_id"], self.school_course_a.id)
        self.assertEqual(notif.meta["school_course_name"], "1A Norte")
        self.assertNotIn("curso", notif.meta)
        self.assertIn("1A Norte", notif.descripcion)
        dest_ids = set(Notificacion.objects.filter(tipo="evento").values_list("destinatario_id", flat=True))
        self.assertIn(self.padre_a.id, dest_ids)
        self.assertNotIn(self.padre_b.id, dest_ids)

    def test_crear_evento_rechaza_curso_legacy(self):
        self.client.force_authenticate(user=self.profesor)

        res = self.client.post(
            "/api/eventos/",
            {
                "titulo": "Reunion Legacy",
                "fecha": "2026-03-21",
                "descripcion": "Reunion con curso legacy",
                "curso": "1A",
                "tipo_evento": "Acto",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            res.json()["detail"],
            "El par\u00e1metro 'curso' est\u00e1 deprecado en este endpoint. Usa school_course_id.",
        )

    def test_crear_evento_acepta_school_course_id_sin_curso(self):
        self.client.force_authenticate(user=self.profesor)

        res = self.client.post(
            "/api/eventos/",
            {
                "titulo": "Reunion Norte por id",
                "fecha": "2026-03-24",
                "descripcion": "Reunion de curso por school_course_id",
                "school_course_id": self.school_course_a.id,
                "tipo_evento": "Acto",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 201)
        evento = Evento.objects.get(titulo="Reunion Norte por id")
        self.assertEqual(evento.curso, "1A")
        self.assertEqual(evento.school_course_id, self.school_course_a.id)

    def test_padre_solo_lista_eventos_de_su_school_course(self):
        Evento.objects.create(
            school=self.school_a,
            titulo="Acto Hijo Norte",
            descripcion="Evento Norte",
            curso="1A",
            fecha="2026-03-22",
            tipo_evento="Acto",
        )
        Evento.objects.create(
            school=self.school_b,
            titulo="Acto Hijo Sur",
            descripcion="Evento Sur",
            curso="1A",
            fecha="2026-03-22",
            tipo_evento="Acto",
        )
        self.client.force_authenticate(user=self.padre_a)

        res = self.client.get(f"/api/padres/hijos/EVA001/eventos/")

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertNotIn("ok", body)
        titles = [item["title"] for item in body["results"]]
        self.assertEqual(titles, ["Acto Hijo Norte"])
        self.assertNotIn("curso", body)
        self.assertEqual(body["school_course_id"], self.school_course_a.id)
        self.assertEqual(body["school_course_name"], "1A Norte")
        self.assertEqual(body["results"][0]["school_course_name"], "1A Norte")
        self.assertEqual(body["results"][0]["extendedProps"]["school_course_name"], "1A Norte")
        self.assertNotIn("curso", body["results"][0]["extendedProps"])
        self.assertNotIn("curso_nombre", body["results"][0]["extendedProps"])

    def test_padre_mis_hijos_eventos_no_expone_cursos_legacy(self):
        Evento.objects.create(
            school=self.school_a,
            school_course=self.school_course_a,
            titulo="Acto conjunto Norte",
            descripcion="Evento Norte",
            curso="1A",
            fecha="2026-03-23",
            tipo_evento="Acto",
        )
        Evento.objects.create(
            school=self.school_a,
            school_course=self.school_course_a_2,
            titulo="Acto otro curso Norte",
            descripcion="Evento Norte 2A",
            curso="2A",
            fecha="2026-03-23",
            tipo_evento="Acto",
        )
        Evento.objects.create(
            school=self.school_b,
            school_course=self.school_course_b,
            titulo="Acto conjunto Sur",
            descripcion="Evento Sur",
            curso="1A",
            fecha="2026-03-23",
            tipo_evento="Acto",
        )
        self.client.force_authenticate(user=self.padre_a)

        res = self.client.get("/api/padres/mis-hijos/eventos/")

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertNotIn("ok", body)
        self.assertNotIn("cursos", body)
        self.assertEqual(
            [item["title"] for item in body["results"]],
            ["Acto conjunto Norte"],
        )
        self.assertEqual(body["results"][0]["school_course_id"], self.school_course_a.id)
        self.assertEqual(body["results"][0]["school_course_name"], "1A Norte")

    def test_superuser_crea_evento_all_con_school_course_en_cada_fila(self):
        superuser = _make_user("super_eventos_all", [])
        superuser.is_superuser = True
        superuser.is_staff = True
        superuser.save(update_fields=["is_superuser", "is_staff"])
        self.client.force_authenticate(user=superuser)

        res = self.client.post(
            "/api/eventos/",
            {
                "titulo": "Semana Institucional",
                "fecha": "2026-03-23",
                "descripcion": "Evento general",
                "curso": "ALL",
                "tipo_evento": "Acto",
            },
            format="json",
            HTTP_X_SCHOOL=self.school_a.slug,
        )

        self.assertEqual(res.status_code, 201)
        eventos = list(Evento.objects.filter(school=self.school_a, titulo="Semana Institucional").order_by("curso"))
        self.assertEqual([ev.curso for ev in eventos], ["1A", "2A"])
        self.assertEqual(
            [ev.school_course_id for ev in eventos],
            list(SchoolCourse.objects.filter(school=self.school_a).order_by("code").values_list("id", flat=True)),
        )

    def test_preceptor_no_puede_crear_evento_en_otro_curso_del_mismo_colegio(self):
        self.client.force_authenticate(user=self.preceptor)

        res = self.client.post(
            "/api/eventos/",
            {
                "titulo": "Reunion 2A",
                "fecha": "2026-03-26",
                "descripcion": "Evento fuera de curso",
                "school_course_id": self.school_course_a_2.id,
                "tipo_evento": "Acto",
            },
            format="json",
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No tenÃ©s permiso para crear eventos en este curso.")
        self.assertFalse(Evento.objects.filter(titulo="Reunion 2A").exists())

    def test_preceptor_sin_asignacion_no_puede_listar_eventos(self):
        Evento.objects.create(
            school=self.school_a,
            school_course=self.school_course_a,
            titulo="Acto Norte preceptor bloqueado",
            descripcion="Evento Norte",
            curso="1A",
            fecha="2026-03-31",
            tipo_evento="Acto",
        )
        self.client.force_authenticate(user=self.preceptor_sin_asignacion)

        res = self.client.get("/api/eventos/", {"school": self.school_a.slug})

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No tenes cursos asignados para ver eventos.")

    def test_preceptor_no_puede_editar_evento_de_otro_curso(self):
        evento = Evento.objects.create(
            school=self.school_a,
            school_course=self.school_course_a_2,
            titulo="Evento 2A",
            descripcion="Evento fuera de curso",
            curso="2A",
            fecha="2026-03-27",
            tipo_evento="Acto",
        )
        self.client.force_authenticate(user=self.preceptor)

        res = self.client.patch(
            f"/api/eventos/editar/{evento.id}/",
            {"titulo": "Editado"},
            format="json",
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No tenÃ©s permiso para editar eventos de este curso.")
        evento.refresh_from_db()
        self.assertEqual(evento.titulo, "Evento 2A")

    def test_editar_evento_acepta_school_course_id(self):
        superuser = _make_user("super_eventos_editar", [])
        superuser.is_superuser = True
        superuser.is_staff = True
        superuser.save(update_fields=["is_superuser", "is_staff"])
        evento = Evento.objects.create(
            school=self.school_a,
            school_course=self.school_course_a,
            titulo="Evento editable",
            descripcion="Evento para cambiar curso",
            curso="1A",
            fecha="2026-03-27",
            tipo_evento="Acto",
        )
        self.client.force_authenticate(user=superuser)

        res = self.client.patch(
            f"/api/eventos/editar/{evento.id}/",
            {"school_course_id": self.school_course_a_2.id},
            format="json",
            HTTP_X_SCHOOL=self.school_a.slug,
        )

        self.assertEqual(res.status_code, 200)
        evento.refresh_from_db()
        self.assertEqual(evento.school_course_id, self.school_course_a_2.id)
        self.assertEqual(evento.curso, "2A")

    def test_editar_evento_rechaza_curso_legacy(self):
        superuser = _make_user("super_eventos_editar_legacy", [])
        superuser.is_superuser = True
        superuser.is_staff = True
        superuser.save(update_fields=["is_superuser", "is_staff"])
        evento = Evento.objects.create(
            school=self.school_a,
            school_course=self.school_course_a,
            titulo="Evento editable legacy",
            descripcion="Evento para legacy",
            curso="1A",
            fecha="2026-03-27",
            tipo_evento="Acto",
        )
        self.client.force_authenticate(user=superuser)

        res = self.client.patch(
            f"/api/eventos/editar/{evento.id}/",
            {"curso": "2A"},
            format="json",
            HTTP_X_SCHOOL=self.school_a.slug,
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            res.json()["detail"],
            "El par\u00e1metro 'curso' est\u00e1 deprecado en este endpoint. Usa school_course_id.",
        )

    def test_preceptor_no_puede_eliminar_evento_de_otro_curso(self):
        evento = Evento.objects.create(
            school=self.school_a,
            school_course=self.school_course_a_2,
            titulo="Eliminar 2A",
            descripcion="Evento fuera de curso",
            curso="2A",
            fecha="2026-03-28",
            tipo_evento="Acto",
        )
        self.client.force_authenticate(user=self.preceptor)

        res = self.client.delete(f"/api/eventos/eliminar/{evento.id}/")

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No tenÃ©s permiso para eliminar eventos de este curso.")
        self.assertTrue(Evento.objects.filter(id=evento.id).exists())


    def test_preceptor_puede_eliminar_evento_de_su_curso_sin_wrapper_ok(self):
        evento = Evento.objects.create(
            school=self.school_a,
            school_course=self.school_course_a,
            titulo="Eliminar 1A",
            descripcion="Evento permitido",
            curso="1A",
            fecha="2026-03-28",
            tipo_evento="Acto",
        )
        self.client.force_authenticate(user=self.preceptor)

        res = self.client.delete(f"/api/eventos/eliminar/{evento.id}/")

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertNotIn("ok", body)
        self.assertEqual(body["id"], evento.id)
        self.assertFalse(Evento.objects.filter(id=evento.id).exists())


@override_settings(SECURE_SSL_REDIRECT=False)
class EventoSerializerContractTests(TestCase):
    def test_serializer_no_expone_curso_y_usa_school_course_name(self):
        school = School.objects.create(name="Colegio Evento Serializer", slug="colegio-evento-serializer")
        creador = _make_user("creador_evento_serializer", ["Profesores"])
        school_course = SchoolCourse.objects.create(
            school=school,
            code="1A",
            name="1A Norte",
            sort_order=1,
        )
        evento = Evento.objects.create(
            school=school,
            school_course=school_course,
            titulo="Acto",
            descripcion="Descripcion",
            curso="1A",
            fecha="2026-03-28",
            tipo_evento="Acto",
            creado_por=creador,
        )

        data = EventoSerializer(evento).data

        self.assertNotIn("curso", data)
        self.assertEqual(data["school_course_id"], school_course.id)
        self.assertEqual(data["school_course_name"], "1A Norte")
        self.assertEqual(data["creado_por"], creador.username)
