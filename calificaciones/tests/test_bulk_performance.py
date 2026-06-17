from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from calificaciones.api_asistencias import _bulk_upsert_asistencias
from calificaciones.models import Alumno, Asistencia, School, SchoolCourse


class BulkPerformanceTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Colegio Rendimiento",
            short_name="Rendimiento",
            slug="colegio-rendimiento",
        )
        self.course = SchoolCourse.objects.create(
            school=self.school,
            code="1A",
            name="1A Rendimiento",
            sort_order=1,
        )
        self.students = Alumno.objects.bulk_create(
            [
                Alumno(
                    school=self.school,
                    school_course=self.course,
                    nombre=f"Alumno {index}",
                    apellido="Carga",
                    id_alumno=f"PERF{index:03d}",
                    curso=self.course.code,
                )
                for index in range(100)
            ]
        )
        self.student_ids = [student.id for student in self.students]
        self.states = {
            student_id: {
                "presente": index % 3 != 0,
                "tarde": index % 3 == 1,
            }
            for index, student_id in enumerate(self.student_ids)
        }

    def test_bulk_asistencias_crea_cien_registros_con_presupuesto_constante(self):
        with CaptureQueriesContext(connection) as queries:
            result = _bulk_upsert_asistencias(
                self.student_ids,
                timezone.localdate(),
                "clases",
                self.states,
                school=self.school,
            )

        self.assertEqual(result["guardadas"], 100)
        self.assertEqual(result["errores"], 0)
        self.assertEqual(
            Asistencia.objects.filter(
                school=self.school,
                fecha=timezone.localdate(),
                tipo_asistencia="clases",
            ).count(),
            100,
        )
        self.assertLessEqual(len(queries), 8)

    def test_bulk_asistencias_actualiza_cien_registros_con_presupuesto_constante(self):
        _bulk_upsert_asistencias(
            self.student_ids,
            timezone.localdate(),
            "clases",
            self.states,
            school=self.school,
        )
        updated_states = {
            student_id: {"presente": True, "tarde": False}
            for student_id in self.student_ids
        }

        with CaptureQueriesContext(connection) as queries:
            result = _bulk_upsert_asistencias(
                self.student_ids,
                timezone.localdate(),
                "clases",
                updated_states,
                school=self.school,
            )

        self.assertEqual(result["guardadas"], 100)
        self.assertFalse(
            Asistencia.objects.filter(
                school=self.school,
                fecha=timezone.localdate(),
                tipo_asistencia="clases",
                presente=False,
            ).exists()
        )
        self.assertLessEqual(len(queries), 8)
