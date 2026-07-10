from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from django.contrib.auth import get_user_model

from calificaciones.models import (
    Alumno,
    Asistencia,
    Evento,
    Mensaje,
    Nota,
    Notificacion,
    Sancion,
    School,
    SchoolCourse,
)
from calificaciones.models_preceptores import PreceptorCurso, ProfesorCurso, SchoolAdmin, SchoolMembership


class SeedQaDataTests(TestCase):
    def test_seed_is_idempotent_even_with_duplicate_sample_note(self):
        call_command("seed_qa_data", "--reset-passwords", verbosity=0)

        school = School.objects.get(slug="qa-local")
        sample_note = Nota.objects.filter(school=school, observaciones="Nota QA local").first()
        self.assertIsNotNone(sample_note)
        sample_note.pk = None
        sample_note.save()
        extra_course = SchoolCourse.objects.create(
            school=school,
            code="EXTRA",
            name="Curso extra",
            sort_order=99,
            is_active=True,
        )
        preceptor = get_user_model().objects.get(username="qa_preceptor")
        PreceptorCurso.objects.create(
            school=school,
            school_course=extra_course,
            preceptor=preceptor,
            curso=extra_course.code,
        )

        models = (Alumno, Nota, Asistencia, Sancion, Evento, Mensaje, Notificacion)
        before = {model: model.objects.filter(school=school).count() for model in models}

        call_command("seed_qa_data", "--reset-passwords", verbosity=0)

        after = {model: model.objects.filter(school=school).count() for model in models}
        self.assertEqual(after, before)
        self.assertFalse(
            PreceptorCurso.objects.filter(
                school=school,
                preceptor=preceptor,
                school_course=extra_course,
            ).exists()
        )

    def test_reset_e2e_data_rebuilds_canonical_school_and_removes_temporary_users(self):
        call_command("seed_qa_data", "--reset-passwords", verbosity=0)

        school = School.objects.get(slug="qa-local")
        other_school = School.objects.create(name="Colegio Persistente", slug="colegio-persistente")
        other_course = SchoolCourse.objects.create(
            school=other_school,
            code="KEEP",
            name="Curso persistente",
            sort_order=1,
            is_active=True,
        )
        Alumno.objects.create(
            school=other_school,
            school_course=other_course,
            curso=other_course.code,
            nombre="Alumno",
            apellido="Persistente",
            id_alumno="KEEP001",
        )

        temporary_user = get_user_model().objects.create_user(
            username="qa_ui_temporal",
            password="QaLocal123!",
        )
        temporary_course = SchoolCourse.objects.create(
            school=school,
            code="QAC99999999",
            name="Curso E2E temporal",
            sort_order=99,
            is_active=True,
        )
        Alumno.objects.create(
            school=school,
            school_course=temporary_course,
            curso=temporary_course.code,
            nombre="Alumno",
            apellido="Temporal",
            id_alumno="LEG99999999",
            padre=temporary_user,
        )

        call_command("seed_qa_data", "--reset-passwords", "--reset-e2e-data", verbosity=0)

        rebuilt_school = School.objects.get(slug="qa-local")
        self.assertEqual(
            set(SchoolCourse.objects.filter(school=rebuilt_school).values_list("code", flat=True)),
            {"1A", "2A"},
        )
        self.assertEqual(
            set(Alumno.objects.filter(school=rebuilt_school).values_list("id_alumno", flat=True)),
            {"QA001", "QA002"},
        )
        self.assertEqual(Nota.objects.filter(school=rebuilt_school).count(), 2)
        self.assertEqual(Asistencia.objects.filter(school=rebuilt_school).count(), 2)
        self.assertEqual(Sancion.objects.filter(school=rebuilt_school).count(), 1)
        self.assertEqual(Evento.objects.filter(school=rebuilt_school).count(), 1)
        self.assertEqual(Mensaje.objects.filter(school=rebuilt_school).count(), 2)
        self.assertEqual(Notificacion.objects.filter(school=rebuilt_school).count(), 1)
        self.assertEqual(ProfesorCurso.objects.filter(school=rebuilt_school).count(), 1)
        self.assertEqual(PreceptorCurso.objects.filter(school=rebuilt_school).count(), 2)
        self.assertEqual(SchoolAdmin.objects.filter(school=rebuilt_school).count(), 2)
        self.assertTrue(
            SchoolMembership.objects.filter(
                school=rebuilt_school,
                user__username="qa_directivo",
            ).exists()
        )
        self.assertFalse(get_user_model().objects.filter(username="qa_ui_temporal").exists())

        self.assertTrue(School.objects.filter(pk=other_school.pk).exists())
        self.assertTrue(SchoolCourse.objects.filter(pk=other_course.pk).exists())
        self.assertTrue(Alumno.objects.filter(school=other_school, id_alumno="KEEP001").exists())

    def test_reset_e2e_data_rejects_non_qa_school_slug(self):
        with self.assertRaises(CommandError):
            call_command(
                "seed_qa_data",
                "--school-slug",
                "colegio-real",
                "--reset-e2e-data",
                verbosity=0,
            )
