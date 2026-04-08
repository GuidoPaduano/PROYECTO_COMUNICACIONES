from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from calificaciones.admin import (
    AlumnoAdmin,
    AsistenciaAdmin,
    CustomUserAdmin,
    NotaAdmin,
    PreceptorCursoAdmin,
    ProfesorCursoAdmin,
    SchoolAdmin,
    SancionAdmin,
)
from calificaciones.forms import EventoForm, SchoolAdminForm
from calificaciones.forms_user import CustomUserChangeForm
from calificaciones.models import Alumno, Asistencia, Evento, Nota, Sancion, School, SchoolCourse
from calificaciones.models_preceptores import PreceptorCurso, ProfesorCurso


def _make_superuser(username: str):
    User = get_user_model()
    return User.objects.create_user(
        username=username,
        password="test1234",
        is_superuser=True,
        is_staff=True,
    )


class CustomUserChangeFormSchoolTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.factory = RequestFactory()
        self.admin_user = _make_superuser("admin_forms_school")
        self.target_user = User.objects.create_user(username="target_forms_school", password="test1234")
        self.school_a = School.objects.create(name="Colegio Admin Norte", slug="colegio-admin-norte")
        self.school_b = School.objects.create(name="Colegio Admin Sur", slug="colegio-admin-sur")
        SchoolCourse.objects.create(school=self.school_a, code="1A", name="1A Norte", sort_order=1)
        SchoolCourse.objects.create(school=self.school_a, code="2A", name="2A Norte", sort_order=2)
        SchoolCourse.objects.create(school=self.school_b, code="1A", name="1A Sur", sort_order=1)
        self.alumno_a = Alumno.objects.create(
            school=self.school_a,
            nombre="Ana",
            apellido="Admin",
            id_alumno="ADM001",
            curso="1A",
        )
        self.alumno_b = Alumno.objects.create(
            school=self.school_b,
            nombre="Bruno",
            apellido="Admin",
            id_alumno="ADM002",
            curso="1A",
        )

    def test_form_usa_school_del_request_para_filtrar_alumnos_y_cursos(self):
        request = self.factory.get("/admin/auth/user/1/change/", {"school": self.school_a.slug})
        request.user = self.admin_user

        form = CustomUserChangeForm(instance=self.target_user, request=request)

        self.assertEqual(form.fields["school"].initial, self.school_a.id)
        self.assertEqual(
            list(form.fields["alumno"].queryset.values_list("id", flat=True)),
            [self.alumno_a.id],
        )
        self.assertEqual(
            form.fields["curso"].choices,
            [("", "---------"), ("1A", "1A Norte"), ("2A", "2A Norte")],
        )

    def test_form_toma_school_del_alumno_vinculado_si_no_hay_request(self):
        self.alumno_b.usuario = self.target_user
        self.alumno_b.save(update_fields=["usuario"])

        form = CustomUserChangeForm(instance=self.target_user)

        self.assertEqual(form.fields["school"].initial, self.school_b.id)
        self.assertEqual(getattr(form.fields["alumno"].initial, "id", None), self.alumno_b.id)
        self.assertEqual(
            list(form.fields["alumno"].queryset.values_list("id", flat=True)),
            [self.alumno_b.id],
        )

    def test_form_rechaza_alumno_de_otro_school(self):
        form = CustomUserChangeForm(
            data={
                "username": self.target_user.username,
                "password": self.target_user.password,
                "school": str(self.school_a.id),
                "curso": "1A",
                "alumno": str(self.alumno_b.id),
            },
            instance=self.target_user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("alumno", form.errors)


class CustomUserAdminRequestInjectionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.factory = RequestFactory()
        self.admin_user = _make_superuser("admin_forms_injection")
        self.target_user = User.objects.create_user(username="target_forms_injection", password="test1234")
        self.school = School.objects.create(name="Colegio Admin Oeste", slug="colegio-admin-oeste")
        SchoolCourse.objects.create(school=self.school, code="1A", name="1A Oeste", sort_order=1)
        self.alumno = Alumno.objects.create(
            school=self.school,
            nombre="Olga",
            apellido="Admin",
            id_alumno="ADM900",
            curso="1A",
        )

    def test_user_admin_inyecta_request_en_el_form(self):
        site = AdminSite()
        model_admin = CustomUserAdmin(get_user_model(), site)
        request = self.factory.get("/admin/auth/user/1/change/", {"school": self.school.slug})
        request.user = self.admin_user

        form_class = model_admin.get_form(request, obj=self.target_user)
        form = form_class(instance=self.target_user)

        self.assertEqual(form.fields["school"].initial, self.school.id)
        self.assertEqual(
            list(form.fields["alumno"].queryset.values_list("id", flat=True)),
            [self.alumno.id],
        )


class EventoFormSchoolTests(TestCase):
    def setUp(self):
        self.school_a = School.objects.create(name="Colegio Eventos Form Norte", slug="colegio-eventos-form-norte")
        self.school_b = School.objects.create(name="Colegio Eventos Form Sur", slug="colegio-eventos-form-sur")
        self.course_a1 = SchoolCourse.objects.create(school=self.school_a, code="1A", name="1A Norte", sort_order=1)
        self.course_a2 = SchoolCourse.objects.create(school=self.school_a, code="2A", name="2A Norte", sort_order=2)
        self.course_b1 = SchoolCourse.objects.create(school=self.school_b, code="1A", name="1A Sur", sort_order=1)

    def test_evento_form_usa_catalogo_del_school_activo(self):
        form = EventoForm(school=self.school_a)

        self.assertEqual(
            form.fields["school_course_id"].choices,
            [("", "Selecciona un curso..."), (str(self.course_a1.id), "1A Norte"), (str(self.course_a2.id), "2A Norte")],
        )

    def test_evento_form_toma_school_del_evento_existente(self):
        evento = Evento.objects.create(
            school=self.school_b,
            titulo="Acto Sur",
            descripcion="Evento Sur",
            curso="1A",
            fecha="2026-03-27",
            tipo_evento="Acto",
        )

        form = EventoForm(instance=evento)

        self.assertEqual(form.fields["school_course_id"].choices, [("", "Selecciona un curso..."), (str(self.course_b1.id), "1A Sur")])
        self.assertEqual(form.fields["school_course_id"].initial, str(self.course_b1.id))

    def test_evento_form_guarda_school_course_desde_id(self):
        form = EventoForm(
            data={
                "titulo": "Acto Norte",
                "descripcion": "Evento con school_course_id",
                "fecha": "2026-03-27",
                "school_course_id": str(self.course_a2.id),
                "tipo_evento": "Acto",
            },
            school=self.school_a,
        )

        self.assertTrue(form.is_valid(), form.errors)
        evento = form.save(commit=False)
        evento.school = self.school_a
        evento.save()

        self.assertEqual(evento.school_course_id, self.course_a2.id)
        self.assertEqual(evento.curso, "2A")


class SchoolAdminBrandingTests(TestCase):
    def setUp(self):
        self.site = AdminSite()
        self.school = School.objects.create(
            name="Escuela Branding",
            slug="escuela-branding",
            short_name="Brand",
            logo_url="/imagenes/logo-brand.png",
            primary_color="#112233",
            accent_color="#445566",
        )

    def test_school_admin_form_normaliza_branding(self):
        form = SchoolAdminForm(
            data={
                "name": "Escuela Branding",
                "short_name": "  Brand  ",
                "slug": "escuela-branding",
                "logo_url": "  /imagenes/logo-brand.png  ",
                "primary_color": "  #aa11bb  ",
                "accent_color": "#cc22dd",
                "is_active": "on",
            },
            instance=self.school,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["short_name"], "Brand")
        self.assertEqual(form.cleaned_data["logo_url"], "/imagenes/logo-brand.png")
        self.assertEqual(form.cleaned_data["primary_color"], "#AA11BB")
        self.assertEqual(form.cleaned_data["accent_color"], "#CC22DD")

    def test_school_admin_muestra_previews_con_fallback(self):
        school = School.objects.create(name="Escuela Fallback", slug="escuela-fallback")
        admin_instance = SchoolAdmin(School, self.site)

        palette_html = admin_instance.branding_palette(school)
        logo_html = admin_instance.logo_preview(school)

        self.assertIn("#0C1B3F", palette_html)
        self.assertIn("#1D4ED8", palette_html)
        self.assertIn("/imagenes/Logo%20Color.png", logo_html)


class AdminSchoolCourseConfigTests(TestCase):
    def setUp(self):
        self.site = AdminSite()
        self.school = School.objects.create(name="Colegio Admin Cursos", slug="colegio-admin-cursos")
        self.school_course = SchoolCourse.objects.create(school=self.school, code="1A", name="1A Admin", sort_order=1)
        self.alumno = Alumno.objects.create(
            school=self.school,
            nombre="Ariel",
            apellido="Admin",
            id_alumno="ADM777",
            curso="1A",
        )
        self.nota = Nota.objects.create(
            school=self.school,
            alumno=self.alumno,
            materia="Lengua",
            tipo="Examen",
            calificacion="8",
            cuatrimestre=1,
            fecha="2026-03-27",
        )
        self.sancion = Sancion.objects.create(
            school=self.school,
            alumno=self.alumno,
            tipo="AmonestaciÃ³n",
            motivo="Observacion",
            fecha="2026-03-27",
            docente="Preceptor",
        )
        self.asistencia = Asistencia.objects.create(
            school=self.school,
            alumno=self.alumno,
            fecha="2026-03-27",
            tipo_asistencia="clases",
            presente=True,
        )
        User = get_user_model()
        self.preceptor = User.objects.create_user(username="preceptor_admin_cfg", password="test1234")
        self.profesor = User.objects.create_user(username="profesor_admin_cfg", password="test1234")
        self.preceptor_curso = PreceptorCurso.objects.create(school=self.school, preceptor=self.preceptor, curso="1A")
        self.profesor_curso = ProfesorCurso.objects.create(school=self.school, profesor=self.profesor, curso="1A")

    def test_admins_priorizan_school_course_en_filtros(self):
        self.assertIn("school_course", AlumnoAdmin(Alumno, self.site).list_filter)
        self.assertIn("alumno__school_course", NotaAdmin(Nota, self.site).list_filter)
        self.assertIn("alumno__school_course", SancionAdmin(Sancion, self.site).list_filter)
        self.assertIn("alumno__school_course", AsistenciaAdmin(Asistencia, self.site).list_filter)
        self.assertIn("school_course", PreceptorCursoAdmin(PreceptorCurso, self.site).list_filter)
        self.assertIn("school_course", ProfesorCursoAdmin(ProfesorCurso, self.site).list_filter)

    def test_admin_helpers_muestran_curso_desde_school_course(self):
        self.assertEqual(NotaAdmin(Nota, self.site).curso_del_alumno(self.nota), "1A")
        self.assertEqual(str(NotaAdmin(Nota, self.site).school_course_del_alumno(self.nota)), str(self.school_course))
        self.assertEqual(SancionAdmin(Sancion, self.site).curso_del_alumno(self.sancion), "1A")
        self.assertEqual(AsistenciaAdmin(Asistencia, self.site).curso_del_alumno(self.asistencia), "1A")
