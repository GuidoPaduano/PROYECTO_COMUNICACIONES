from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.test.utils import override_settings
from rest_framework.test import APIClient

from calificaciones.alerts import evaluar_alerta_nota, reconciliar_alertas_academicas
from calificaciones.models import AlertaAcademica, Alumno, Nota, Notificacion, School, SchoolCourse
from calificaciones.models_preceptores import PreceptorCurso, ProfesorCurso


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
        ProfesorCurso.objects.create(profesor=self.profesor, curso="1A")
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
        self.assertEqual(row["alumno"]["school_course_name"], "1A")
        self.assertNotIn("curso", row["alumno"])

    def test_mejora_en_la_misma_materia_cierra_alerta_activa(self):
        res_bad = self._post_nota(resultado="TED", calificacion="TED", fecha_iso="2026-03-01", materia="Lengua")
        self.assertEqual(res_bad.status_code, 201)
        self.assertEqual(AlertaAcademica.objects.filter(estado="activa").count(), 1)

        res_good = self._post_nota(resultado="TEA", calificacion="TEA", fecha_iso="2026-03-02", materia="Lengua")
        self.assertEqual(res_good.status_code, 201)

        alerta = AlertaAcademica.objects.get()
        self.assertEqual(alerta.estado, "cerrada")

        self.client.force_authenticate(user=self.preceptor)
        res = self.client.get("/api/preceptor/alertas-academicas/?limit=10")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["count"], 0)

    def test_endpoint_cierra_alerta_vieja_si_ya_no_hay_trigger(self):
        self._post_nota(resultado="TEA", calificacion="TEA", fecha_iso="2026-03-01", materia="Lengua")
        AlertaAcademica.objects.create(
            alumno=self.alumno,
            materia="Lengua",
            cuatrimestre=1,
            severidad=1,
            riesgo_ponderado="1.000",
            triggers={"materia": "Lengua", "A_TED_critico": True},
            estado="activa",
        )

        self.client.force_authenticate(user=self.preceptor)
        res = self.client.get("/api/preceptor/alertas-academicas/?limit=10")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["count"], 0)
        self.assertEqual(AlertaAcademica.objects.filter(estado="activa").count(), 0)


@override_settings(SECURE_SSL_REDIRECT=False)
class AlertasAcademicasSchoolRecipientTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.school_a = School.objects.create(name="Colegio Alertas Norte", slug="colegio-alertas-norte")
        self.school_b = School.objects.create(name="Colegio Alertas Sur", slug="colegio-alertas-sur")
        self.school_course_a = SchoolCourse.objects.create(school=self.school_a, code="1A", name="1A Norte", sort_order=1)
        self.school_course_b = SchoolCourse.objects.create(school=self.school_b, code="1A", name="1A Sur", sort_order=1)
        self.preceptor_a = _make_user("preceptor_alerta_a", ["Preceptores"])
        self.preceptor_b = _make_user("preceptor_alerta_b", ["Preceptores"])
        self.alumno = Alumno.objects.create(
            school=self.school_a,
            school_course=self.school_course_a,
            nombre="Luz",
            apellido="Perez",
            id_alumno="LEGAL900",
            curso="1A",
        )
        PreceptorCurso.objects.create(
            school=self.school_a,
            preceptor=self.preceptor_a,
            curso="1A",
        )
        PreceptorCurso.objects.create(
            school=self.school_b,
            preceptor=self.preceptor_b,
            curso="1A",
        )

    def test_notifica_solo_al_preceptor_del_mismo_school(self):
        nota = Nota.objects.create(
            school=self.school_a,
            alumno=self.alumno,
            materia="Lengua",
            tipo="Examen",
            resultado="TED",
            calificacion="TED",
            cuatrimestre=1,
            fecha="2026-03-05",
        )

        info = evaluar_alerta_nota(nota=nota, send_email=False)

        self.assertTrue(info["created"])
        notif = Notificacion.objects.filter(meta__es_alerta_academica=True, destinatario=self.preceptor_a).latest("id")
        self.assertEqual(notif.meta["school_course_name"], "1A Norte")
        self.assertNotIn("curso", notif.meta)
        self.assertIn("1A Norte", notif.descripcion)
        dest_ids = set(
            Notificacion.objects.filter(meta__es_alerta_academica=True).values_list("destinatario_id", flat=True)
        )
        self.assertIn(self.preceptor_a.id, dest_ids)
        self.assertNotIn(self.preceptor_b.id, dest_ids)

    def test_endpoint_preceptor_no_mezcla_alertas_de_otro_school_con_mismo_codigo(self):
        alumno_b = Alumno.objects.create(
            school=self.school_b,
            school_course=self.school_course_b,
            nombre="Nora",
            apellido="Suarez",
            id_alumno="LEGAL901",
            curso="1A",
        )
        nota_a = Nota.objects.create(
            school=self.school_a,
            alumno=self.alumno,
            materia="Lengua",
            tipo="Examen",
            resultado="TED",
            calificacion="TED",
            cuatrimestre=1,
            fecha="2026-03-06",
        )
        nota_b = Nota.objects.create(
            school=self.school_b,
            alumno=alumno_b,
            materia="Lengua",
            tipo="Examen",
            resultado="TED",
            calificacion="TED",
            cuatrimestre=1,
            fecha="2026-03-06",
        )
        evaluar_alerta_nota(nota=nota_a, send_email=False)
        evaluar_alerta_nota(nota=nota_b, send_email=False)

        self.client.force_authenticate(user=self.preceptor_a)
        res = self.client.get(
            "/api/preceptor/alertas-academicas/?limit=10",
            HTTP_X_SCHOOL=self.school_a.slug,
        )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["alumno"]["id"], self.alumno.id)
        self.assertEqual(body["results"][0]["alumno"]["school_course_name"], "1A Norte")

    def test_reconciliar_alertas_academicas_legacy_por_curso_respeta_school(self):
        alumno_b = Alumno.objects.create(
            school=self.school_b,
            school_course=self.school_course_b,
            nombre="Nora",
            apellido="Suarez",
            id_alumno="LEGAL901",
            curso="1A",
        )
        alerta_a = AlertaAcademica.objects.create(
            alumno=self.alumno,
            materia="Lengua",
            cuatrimestre=1,
            severidad=1,
            riesgo_ponderado="1.000",
            triggers={"materia": "Lengua", "A_TED_critico": True},
            estado="activa",
        )
        alerta_b = AlertaAcademica.objects.create(
            alumno=alumno_b,
            materia="Lengua",
            cuatrimestre=1,
            severidad=1,
            riesgo_ponderado="1.000",
            triggers={"materia": "Lengua", "A_TED_critico": True},
            estado="activa",
        )

        info = reconciliar_alertas_academicas(cursos=["1A"], school=self.school_a)

        self.assertEqual(info["revisadas"], 1)
        alerta_a.refresh_from_db()
        alerta_b.refresh_from_db()
        self.assertEqual(alerta_a.estado, "cerrada")
        self.assertEqual(alerta_b.estado, "activa")
