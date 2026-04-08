from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.test.utils import override_settings
from rest_framework.test import APIClient

from calificaciones.alerts_inasistencias import evaluar_alerta_inasistencia, evaluar_alertas_inasistencia_por_alumnos
from calificaciones.models import Alumno, Asistencia, Notificacion, AlertaInasistencia, School, SchoolCourse
from calificaciones.models_preceptores import PreceptorCurso, ProfesorCurso


def _make_staff_user(username="staff"):
    User = get_user_model()
    user = User.objects.create_user(
        username=username,
        password="test1234",
        is_staff=True,
        is_superuser=False,
    )
    group, _ = Group.objects.get_or_create(name="Directivos")
    user.groups.add(group)
    return user


def _make_alumno(nombre, apellido, legajo, curso="1A", padre=None, school=None):
    return Alumno.objects.create(
        nombre=nombre,
        apellido=apellido,
        id_alumno=legajo,
        school=school,
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
            "school_course_id": a1.school_course_id,
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
            "school_course_id": a1.school_course_id,
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
            "school_course_id": alumno.school_course_id,
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
            "school_course_id": alumno.school_course_id,
            "fecha": "2026-03-01",
            "tipo_asistencia": "clases",
            "asistencias": {str(alumno.id): "ausente"},
        }
        p2 = {
            "school_course_id": alumno.school_course_id,
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
        self.assertEqual(alerta.school_course_id, alumno.school_course_id)
        self.assertEqual(alerta.motivo, "AUSENCIAS_CONSECUTIVAS")
        self.assertEqual(alerta.estado, "activa")

    def test_endpoint_preceptor_alertas_inasistencias_lista_alumno(self):
        User = get_user_model()
        preceptor = User.objects.create_user(username="preceptor_inas", password="test1234")
        grp, _ = Group.objects.get_or_create(name="Preceptores")
        preceptor.groups.add(grp)

        alumno = _make_alumno("Noa", "Garcia", "LEG401", curso="1A")
        PreceptorCurso.objects.create(preceptor=preceptor, curso="1A")

        alerta = AlertaInasistencia.objects.create(
            alumno=alumno,
            curso="1A",
            tipo_asistencia="clases",
            motivo="AUSENCIAS_CONSECUTIVAS",
            severidad=1,
            valor_actual=2,
            umbral=2,
            estado="activa",
        )
        self.assertEqual(alerta.school_course_id, alumno.school_course_id)

        self.client.force_authenticate(user=preceptor)
        res = self.client.get("/api/preceptor/alertas-inasistencias/?limit=10")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("results", body)
        self.assertGreaterEqual(len(body["results"]), 1)
        self.assertEqual(body["results"][0]["alumno"]["id"], alumno.id)
        self.assertEqual(body["results"][0]["alumno"]["school_course_name"], "1A")
        self.assertNotIn("curso", body["results"][0]["alumno"])
        self.assertIn("total_inasistencias_clases", body["results"][0])

    @override_settings(ALERTAS_INASISTENCIAS_UMBRALES_FALTAS="10,20,25")
    def test_alerta_faltas_acumuladas_al_llegar_a_10(self):
        staff = _make_staff_user("staff_faltas_10")
        alumno = _make_alumno("Mia", "Lopez", "LEG501", curso="1A")
        self.client.force_authenticate(user=staff)

        base = date(2026, 3, 1)
        for i in range(10):
            payload = {
                "school_course_id": alumno.school_course_id,
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
        alerta = AlertaInasistencia.objects.filter(
            alumno=alumno,
            motivo="FALTAS_ACUMULADAS",
            umbral=10,
        ).first()
        self.assertIsNotNone(alerta)
        self.assertEqual(alerta.school_course_id, alumno.school_course_id)


@override_settings(SECURE_SSL_REDIRECT=False)
class FirmaAsistenciaApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.padre = User.objects.create_user(username="padre_firma_asis", password="test1234")
        self.otro = User.objects.create_user(username="otro_firma_asis", password="test1234")
        self.alumno = _make_alumno("Uma", "Rossi", "LEG880", curso="1A", padre=self.padre)
        self.asistencia = Asistencia.objects.create(
            alumno=self.alumno,
            fecha=date(2026, 3, 12),
            tipo_asistencia="clases",
            presente=False,
        )

    def test_padre_puede_firmar_inasistencia_una_vez(self):
        self.client.force_authenticate(user=self.padre)

        res = self.client.post(f"/api/asistencias/{self.asistencia.id}/firmar/", format="json")

        self.assertEqual(res.status_code, 200)
        self.asistencia.refresh_from_db()
        self.assertTrue(self.asistencia.firmada)
        self.assertEqual(self.asistencia.firmada_por_id, self.padre.id)
        self.assertIsNotNone(self.asistencia.firmada_en)

    def test_padre_no_puede_firmar_inasistencia_dos_veces(self):
        self.client.force_authenticate(user=self.padre)
        first = self.client.post(f"/api/asistencias/{self.asistencia.id}/firmar/", format="json")
        self.assertEqual(first.status_code, 200)

        second = self.client.post(f"/api/asistencias/{self.asistencia.id}/firmar/", format="json")

        self.assertEqual(second.status_code, 400)
        self.asistencia.refresh_from_db()
        self.assertTrue(self.asistencia.firmada)

    def test_otro_usuario_no_puede_firmar_inasistencia(self):
        self.client.force_authenticate(user=self.otro)

        res = self.client.post(f"/api/asistencias/{self.asistencia.id}/firmar/", format="json")

        self.assertEqual(res.status_code, 403)
        self.asistencia.refresh_from_db()
        self.assertFalse(self.asistencia.firmada)


@override_settings(SECURE_SSL_REDIRECT=False)
class AsistenciasAccessControlTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.outsider = User.objects.create_user(username="outsider_asis", password="test1234")
        self.staff_sin_rol = User.objects.create_user(
            username="staff_sin_rol_asis",
            password="test1234",
            is_staff=True,
        )
        self.padre = User.objects.create_user(username="padre_asis_access", password="test1234")
        self.padre_otro = User.objects.create_user(username="padre_asis_access_otro", password="test1234")
        self.preceptor = User.objects.create_user(username="preceptor_asis_access", password="test1234")
        self.profesor_otro = User.objects.create_user(username="profesor_asis_access_otro", password="test1234")
        preceptor_group, _ = Group.objects.get_or_create(name="Preceptores")
        profesor_group, _ = Group.objects.get_or_create(name="Profesores")
        self.preceptor.groups.add(preceptor_group)
        self.profesor_otro.groups.add(profesor_group)

        self.school = School.objects.create(name="Colegio Asis Access", slug="colegio-asis-access")
        self.school_course_1a = SchoolCourse.objects.create(
            school=self.school, code="1A", name="1A Norte", sort_order=1
        )
        SchoolCourse.objects.create(school=self.school, code="2A", name="2A Norte", sort_order=2)
        self.alumno = Alumno.objects.create(
            school=self.school,
            nombre="Mia",
            apellido="Sosa",
            id_alumno="LEGACC01",
            curso="1A",
            padre=self.padre,
        )
        Alumno.objects.create(
            school=self.school,
            nombre="Leo",
            apellido="Sosa",
            id_alumno="LEGACC02",
            curso="2A",
            padre=self.padre_otro,
        )
        self.asistencia = Asistencia.objects.create(
            school=self.school,
            alumno=self.alumno,
            fecha=date(2026, 3, 12),
            tipo_asistencia="clases",
            presente=False,
        )
        PreceptorCurso.objects.create(
            school=self.school,
            preceptor=self.preceptor,
            curso="1A",
        )
        ProfesorCurso.objects.create(
            school=self.school,
            profesor=self.profesor_otro,
            curso="2A",
        )

    def test_usuario_sin_rol_no_puede_registrar_asistencias(self):
        self.client.force_authenticate(user=self.outsider)

        res = self.client.post(
            "/api/asistencias/registrar/",
            {
                "school_course_id": self.alumno.school_course_id,
                "fecha": "2026-03-13",
                "tipo_asistencia": "clases",
                "asistencias": {str(self.alumno.id): "ausente"},
            },
            format="json",
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No tenés permisos para ese curso.")

    def test_profesor_de_otro_curso_no_puede_registrar_asistencias(self):
        self.client.force_authenticate(user=self.profesor_otro)

        res = self.client.post(
            "/api/asistencias/registrar/",
            {
                "school_course_id": self.alumno.school_course_id,
                "fecha": "2026-03-13",
                "tipo_asistencia": "clases",
                "asistencias": {str(self.alumno.id): "ausente"},
            },
            format="json",
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No tenés permisos para ese curso.")

    def test_padre_titular_puede_ver_asistencias_de_su_hijo(self):
        self.client.force_authenticate(user=self.padre)

        res = self.client.get(f"/api/asistencias/alumno/{self.alumno.id}/")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["alumno"]["id"], self.alumno.id)

    def test_otro_usuario_no_puede_ver_asistencias_de_alumno(self):
        self.client.force_authenticate(user=self.padre_otro)

        res = self.client.get(f"/api/asistencias/alumno/{self.alumno.id}/")

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No autorizado.")

    def test_staff_sin_rol_no_puede_justificar_asistencia(self):
        self.client.force_authenticate(user=self.staff_sin_rol)

        res = self.client.patch(
            f"/api/asistencias/{self.asistencia.id}/justificar/",
            {"justificada": True},
            format="json",
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No tenés permisos para justificar asistencias.")

    def test_padre_no_puede_editar_detalle_de_asistencia(self):
        self.client.force_authenticate(user=self.padre)

        res = self.client.patch(
            f"/api/asistencias/{self.asistencia.id}/detalle/",
            {"detalle": "Intento invalido"},
            format="json",
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No tenés permisos para editar el detalle de asistencias.")


@override_settings(SECURE_SSL_REDIRECT=False)
class AsistenciasSchoolScopingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = get_user_model().objects.create_user(
            username="admin_asis_school",
            password="test1234",
            is_staff=True,
            is_superuser=True,
        )
        self.padre_a = get_user_model().objects.create_user(
            username="padre_asis_school",
            password="test1234",
        )
        self.school_a = School.objects.create(name="Colegio Asis Norte", slug="colegio-asis-norte")
        self.school_b = School.objects.create(name="Colegio Asis Sur", slug="colegio-asis-sur")
        self.school_course_a = SchoolCourse.objects.create(school=self.school_a, code="1A", name="1A Norte", sort_order=1)
        self.school_course_b = SchoolCourse.objects.create(school=self.school_b, code="1A", name="1A Sur", sort_order=1)
        self.fecha = date(2026, 3, 15)
        self.alumno_a = Alumno.objects.create(
            school=self.school_a,
            nombre="Lara",
            apellido="Diaz",
            id_alumno="LEGAS01",
            curso="1A",
            padre=self.padre_a,
        )
        self.alumno_b = Alumno.objects.create(
            school=self.school_b,
            nombre="Nico",
            apellido="Ruiz",
            id_alumno="LEGAS02",
            curso="1A",
        )
        Asistencia.objects.create(
            school=self.school_a,
            alumno=self.alumno_a,
            fecha=self.fecha,
            tipo_asistencia="clases",
            presente=False,
        )
        Asistencia.objects.create(
            school=self.school_b,
            alumno=self.alumno_b,
            fecha=self.fecha,
            tipo_asistencia="clases",
            presente=True,
        )
        self.client.force_authenticate(user=self.admin)

    def test_asistencias_por_curso_y_fecha_filtra_por_school(self):
        res = self.client.get(
            "/api/asistencias/curso/",
            {"school_course_id": self.school_course_a.id, "fecha": str(self.fecha), "school": self.school_a.slug},
        )

        self.assertEqual(res.status_code, 200)
        items = res.json()["items"]
        self.assertEqual([item["alumno_id"] for item in items], [self.alumno_a.id])

    def test_asistencias_por_curso_y_fecha_rechaza_curso_legacy(self):
        res = self.client.get(
            "/api/asistencias/curso/",
            {"curso": "1A", "fecha": str(self.fecha), "school": self.school_a.slug},
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            res.json()["detail"],
            "El parámetro 'curso' está deprecado en este endpoint. Usa school_course_id.",
        )

    def test_asistencias_por_curso_y_fecha_acepta_school_course_id(self):
        res = self.client.get(
            "/api/asistencias/curso/",
            {"school_course_id": self.school_course_a.id, "fecha": str(self.fecha), "school": self.school_a.slug},
        )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertNotIn("curso", body)
        self.assertEqual(body["school_course_id"], self.school_course_a.id)
        self.assertEqual(body["school_course_name"], "1A Norte")
        self.assertNotIn("curso", body["items"][0])
        self.assertEqual(body["items"][0]["school_course_name"], "1A Norte")
        self.assertEqual([item["alumno_id"] for item in body["items"]], [self.alumno_a.id])

    def test_registrar_asistencias_acepta_school_course_id_sin_curso(self):
        fecha_nueva = self.fecha + timedelta(days=1)
        res = self.client.post(
            "/api/asistencias/registrar/",
            {
                "school_course_id": self.school_course_a.id,
                "fecha": str(fecha_nueva),
                "tipo_asistencia": "clases",
                "asistencias": {str(self.alumno_a.id): "ausente"},
            },
            format="json",
            HTTP_X_SCHOOL=self.school_a.slug,
        )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertNotIn("curso", body)
        self.assertEqual(body["school_course_id"], self.school_course_a.id)
        self.assertEqual(body["school_course_name"], "1A Norte")
        asistencia = Asistencia.objects.get(alumno=self.alumno_a, fecha=fecha_nueva, tipo_asistencia="clases")
        self.assertFalse(asistencia.presente)
        notif = Notificacion.objects.filter(destinatario=self.padre_a, tipo="inasistencia").latest("id")
        self.assertEqual(notif.meta["school_course_id"], self.school_course_a.id)
        self.assertEqual(notif.meta["school_course_name"], "1A Norte")
        self.assertNotIn("curso", notif.meta)
        self.assertIn("1A Norte", notif.descripcion)

    def test_registrar_asistencias_rechaza_curso_legacy_en_formato_map(self):
        fecha_nueva = self.fecha + timedelta(days=1)
        res = self.client.post(
            "/api/asistencias/registrar/",
            {
                "curso": "1A",
                "fecha": str(fecha_nueva),
                "tipo_asistencia": "clases",
                "asistencias": {str(self.alumno_a.id): "ausente"},
            },
            format="json",
            HTTP_X_SCHOOL=self.school_a.slug,
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            res.json()["detail"],
            "El parámetro 'curso' está deprecado en este endpoint. Usa school_course_id.",
        )

    def test_registrar_asistencias_rechaza_curso_legacy_en_formato_presentes(self):
        fecha_nueva = self.fecha + timedelta(days=1)
        res = self.client.post(
            "/api/asistencias/registrar/",
            {
                "curso": "1A",
                "fecha": str(fecha_nueva),
                "tipo_asistencia": "clases",
                "presentes": [self.alumno_a.id],
            },
            format="json",
            HTTP_X_SCHOOL=self.school_a.slug,
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            res.json()["detail"],
            "El parámetro 'curso' está deprecado en este endpoint. Usa school_course_id.",
        )

    def test_registrar_asistencias_rechaza_curso_legacy_en_items_global(self):
        fecha_nueva = self.fecha + timedelta(days=1)
        res = self.client.post(
            "/api/asistencias/registrar/",
            {
                "curso": "1A",
                "fecha": str(fecha_nueva),
                "tipo_asistencia": "clases",
                "items": [
                    {
                        "alumno_id": self.alumno_a.id,
                        "presente": False,
                    }
                ],
            },
            format="json",
            HTTP_X_SCHOOL=self.school_a.slug,
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            res.json()["detail"],
            "El parámetro 'curso' está deprecado en este endpoint. Usa school_course_id.",
        )

    def test_registrar_asistencias_rechaza_curso_legacy_en_items_por_item(self):
        fecha_nueva = self.fecha + timedelta(days=1)
        res = self.client.post(
            "/api/asistencias/registrar/",
            {
                "fecha": str(fecha_nueva),
                "tipo_asistencia": "clases",
                "items": [
                    {
                        "alumno_id": self.alumno_a.id,
                        "curso": "1A",
                        "presente": False,
                    }
                ],
            },
            format="json",
            HTTP_X_SCHOOL=self.school_a.slug,
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            res.json()["detail"],
            "El parámetro 'curso' está deprecado en este endpoint. Usa school_course_id.",
        )

    def test_asistencias_por_alumno_serializa_school_course_name(self):
        res = self.client.get(
            f"/api/asistencias/alumno/{self.alumno_a.id}/",
            {"school": self.school_a.slug},
        )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["alumno"]["id"], self.alumno_a.id)
        self.assertEqual(body["alumno"]["school_course_id"], self.school_course_a.id)
        self.assertEqual(body["alumno"]["school_course_name"], "1A Norte")
        self.assertNotIn("curso", body["alumno"])
        self.assertNotIn("curso", body["results"][0])


@override_settings(SECURE_SSL_REDIRECT=False)
class AsistenciasLegacyPreceptorFallbackTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.preceptor = get_user_model().objects.create_user(
            username="preceptor1",
            password="test1234",
        )
        grp, _ = Group.objects.get_or_create(name="Preceptores")
        self.preceptor.groups.add(grp)
        self.school = School.objects.create(name="Colegio Asis Fallback", slug="colegio-asis-fallback")
        self.school_course = SchoolCourse.objects.create(
            school=self.school,
            code="1A",
            name="1A Norte",
            sort_order=1,
        )
        self.alumno = Alumno.objects.create(
            school=self.school,
            nombre="Lia",
            apellido="Fallback",
            id_alumno="LEGFALL01",
            curso="1A",
        )
        self.client.force_authenticate(user=self.preceptor)

    def test_preceptor_sin_asignacion_no_hereda_curso_por_username(self):
        res = self.client.get(
            "/api/asistencias/curso/",
            {
                "school": self.school.slug,
                "school_course_id": self.school_course.id,
                "fecha": "2026-03-15",
            },
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "No tenés permisos para ese curso.")


@override_settings(SECURE_SSL_REDIRECT=False, ALERTAS_INASISTENCIAS_CONSECUTIVAS=1)
class InasistenciasSchoolRecipientTests(TestCase):
    def setUp(self):
        self.school_a = School.objects.create(name="Colegio Inas Norte", slug="colegio-inas-norte")
        self.school_b = School.objects.create(name="Colegio Inas Sur", slug="colegio-inas-sur")
        self.school_course_a = SchoolCourse.objects.create(school=self.school_a, code="1A", name="1A Norte", sort_order=1)
        self.school_course_b = SchoolCourse.objects.create(school=self.school_b, code="1A", name="1A Sur", sort_order=1)
        User = get_user_model()
        self.preceptor_a = User.objects.create_user(username="preceptor_inas_a", password="test1234")
        self.preceptor_b = User.objects.create_user(username="preceptor_inas_b", password="test1234")
        grp, _ = Group.objects.get_or_create(name="Preceptores")
        self.preceptor_a.groups.add(grp)
        self.preceptor_b.groups.add(grp)
        self.alumno = _make_alumno("Nora", "Diaz", "LEGINA01", curso="1A", school=self.school_a)
        self.alumno.school_course = self.school_course_a
        self.alumno.save(update_fields=["school_course"])
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
        asistencia = Asistencia.objects.create(
            school=self.school_a,
            alumno=self.alumno,
            fecha=date(2026, 3, 20),
            tipo_asistencia="clases",
            presente=False,
            justificada=False,
        )

        info = evaluar_alerta_inasistencia(alumno=self.alumno, asistencia=asistencia)

        self.assertTrue(info["created"])
        alerta = AlertaInasistencia.objects.get(id=info["alerta_id"])
        self.assertEqual(alerta.school_course_id, self.alumno.school_course_id)
        notif = Notificacion.objects.filter(meta__es_alerta_inasistencia=True, destinatario=self.preceptor_a).latest("id")
        self.assertEqual(notif.meta["school_course_name"], "1A Norte")
        self.assertNotIn("curso", notif.meta)
        self.assertIn("1A Norte", notif.descripcion)
        dest_ids = set(
            Notificacion.objects.filter(meta__es_alerta_inasistencia=True).values_list("destinatario_id", flat=True)
        )
        self.assertIn(self.preceptor_a.id, dest_ids)
        self.assertNotIn(self.preceptor_b.id, dest_ids)

    def test_batch_no_mezcla_preceptores_de_otro_school_con_mismo_codigo(self):
        alumno_b = _make_alumno("Olga", "Ruiz", "LEGINA02", curso="1A", school=self.school_b)
        alumno_b.school_course = self.school_course_b
        alumno_b.save(update_fields=["school_course"])

        Asistencia.objects.create(
            school=self.school_a,
            alumno=self.alumno,
            fecha=date(2026, 3, 21),
            tipo_asistencia="clases",
            presente=False,
            justificada=False,
        )
        Asistencia.objects.create(
            school=self.school_b,
            alumno=alumno_b,
            fecha=date(2026, 3, 21),
            tipo_asistencia="clases",
            presente=False,
            justificada=False,
        )

        created = evaluar_alertas_inasistencia_por_alumnos(
            alumno_ids=[self.alumno.id, alumno_b.id],
            tipo_asistencia="clases",
        )

        self.assertEqual(created, 2)
        notifs_a = Notificacion.objects.filter(meta__es_alerta_inasistencia=True, destinatario=self.preceptor_a)
        notifs_b = Notificacion.objects.filter(meta__es_alerta_inasistencia=True, destinatario=self.preceptor_b)
        self.assertEqual(notifs_a.count(), 1)
        self.assertEqual(notifs_b.count(), 1)
        self.assertEqual(notifs_a.get().meta["alumno_id"], self.alumno.id)
        self.assertEqual(notifs_b.get().meta["alumno_id"], alumno_b.id)
