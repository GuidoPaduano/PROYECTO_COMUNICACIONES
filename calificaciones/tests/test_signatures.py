from django.contrib.auth import get_user_model
from django.test import TestCase

from calificaciones.models import Alumno, Nota, School, SchoolCourse
from calificaciones.signatures import claim_signature


class AtomicSignatureTests(TestCase):
    def setUp(self):
        self.padre = get_user_model().objects.create_user(
            username="padre_firma_atomica",
            password="test1234",
        )
        school = School.objects.create(name="Colegio Firma Atomica", slug="colegio-firma-atomica")
        course = SchoolCourse.objects.create(school=school, code="1A", name="1A")
        alumno = Alumno.objects.create(
            school=school,
            school_course=course,
            nombre="Iara",
            apellido="Sosa",
            id_alumno="LEG-ATOMIC-1",
            curso="1A",
            padre=self.padre,
        )
        self.nota = Nota.objects.create(
            school=school,
            alumno=alumno,
            materia="Lengua",
            tipo="Examen",
            calificacion="8",
            cuatrimestre=1,
            fecha="2026-06-14",
        )

    def test_solo_un_snapshot_obsoleto_puede_reclamar_la_firma(self):
        first_request_snapshot = Nota.objects.get(pk=self.nota.pk)
        second_request_snapshot = Nota.objects.get(pk=self.nota.pk)
        self.assertFalse(first_request_snapshot.firmada)
        self.assertFalse(second_request_snapshot.firmada)

        first_claimed = claim_signature(first_request_snapshot, user=self.padre)
        second_claimed = claim_signature(second_request_snapshot, user=self.padre)

        self.assertTrue(first_claimed)
        self.assertFalse(second_claimed)
        self.assertTrue(second_request_snapshot.firmada)
        self.assertEqual(second_request_snapshot.firmada_por_id, self.padre.id)
        self.assertIsNotNone(second_request_snapshot.firmada_en)
