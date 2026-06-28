from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, RequestFactory, override_settings
from rest_framework.test import APIClient

from calificaciones.models import Alumno, Asistencia, Sancion, School, SchoolCourse
from calificaciones.utils_pagination import paginate_queryset, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(username, groups=None, superuser=False):
    User = get_user_model()
    user = User.objects.create_user(username=username, password="test1234", is_superuser=superuser)
    for name in groups or []:
        group, _ = Group.objects.get_or_create(name=name)
        user.groups.add(group)
    return user


def _setup_school():
    school = School.objects.create(name="Colegio Paginacion Test", slug="colegio-paginacion-test")
    school_course = SchoolCourse.objects.create(school=school, code="2A", name="2A", sort_order=1)
    return school, school_course


def _make_alumno(school, school_course, nombre="Juan", apellido="Test", legajo="LEG_PAG_001"):
    return Alumno.objects.create(
        school=school,
        school_course=school_course,
        nombre=nombre,
        apellido=apellido,
        id_alumno=legajo,
        curso="2A",
    )


# ---------------------------------------------------------------------------
# Unit tests: utils_pagination.paginate_queryset
# ---------------------------------------------------------------------------

class PaginateQuerysetUnitTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        school, school_course = _setup_school()
        for i in range(120):
            Alumno.objects.create(
                school=school,
                school_course=school_course,
                nombre=f"Alumno{i}",
                apellido="Test",
                id_alumno=f"LEG_UNIT_{i:03d}",
                curso="2A",
            )
        self.qs = Alumno.objects.filter(school=school).order_by("id")

    def test_primera_pagina_devuelve_page_size_items(self):
        request = self.factory.get("/", {"page": "1"})
        items, meta = paginate_queryset(self.qs, request, default_size=10)
        self.assertEqual(len(list(items)), 10)
        self.assertEqual(meta["page"], 1)
        self.assertEqual(meta["page_size"], 10)
        self.assertEqual(meta["total"], 120)
        self.assertEqual(meta["total_pages"], 12)
        self.assertTrue(meta["has_next"])
        self.assertFalse(meta["has_previous"])

    def test_ultima_pagina_no_tiene_siguiente(self):
        request = self.factory.get("/", {"page": "12"})
        items, meta = paginate_queryset(self.qs, request, default_size=10)
        self.assertEqual(meta["page"], 12)
        self.assertFalse(meta["has_next"])
        self.assertTrue(meta["has_previous"])

    def test_pagina_intermedia_tiene_ambos(self):
        request = self.factory.get("/", {"page": "5"})
        items, meta = paginate_queryset(self.qs, request, default_size=10)
        self.assertEqual(meta["page"], 5)
        self.assertTrue(meta["has_next"])
        self.assertTrue(meta["has_previous"])

    def test_sin_page_param_devuelve_pagina_1(self):
        request = self.factory.get("/")
        items, meta = paginate_queryset(self.qs, request, default_size=10)
        self.assertEqual(meta["page"], 1)

    def test_page_invalido_cae_a_pagina_1(self):
        request = self.factory.get("/", {"page": "abc"})
        items, meta = paginate_queryset(self.qs, request, default_size=10)
        self.assertEqual(meta["page"], 1)

    def test_page_fuera_de_rango_clampea_a_ultima(self):
        request = self.factory.get("/", {"page": "999"})
        items, meta = paginate_queryset(self.qs, request, default_size=10)
        self.assertEqual(meta["page"], meta["total_pages"])

    def test_page_size_custom_respetado(self):
        request = self.factory.get("/", {"page": "1", "page_size": "25"})
        items, meta = paginate_queryset(self.qs, request, default_size=10)
        self.assertEqual(meta["page_size"], 25)
        self.assertEqual(len(list(items)), 25)

    def test_page_size_no_supera_maximo(self):
        request = self.factory.get("/", {"page_size": str(MAX_PAGE_SIZE + 500)})
        items, meta = paginate_queryset(self.qs, request)
        self.assertEqual(meta["page_size"], MAX_PAGE_SIZE)

    def test_items_segunda_pagina_son_distintos_a_primera(self):
        req1 = self.factory.get("/", {"page": "1"})
        req2 = self.factory.get("/", {"page": "2"})
        items1, _ = paginate_queryset(self.qs, req1, default_size=10)
        items2, _ = paginate_queryset(self.qs, req2, default_size=10)
        ids1 = {a.id for a in items1}
        ids2 = {a.id for a in items2}
        self.assertEqual(len(ids1 & ids2), 0)

    def test_queryset_vacio(self):
        request = self.factory.get("/", {"page": "1"})
        empty_qs = Alumno.objects.none()
        items, meta = paginate_queryset(empty_qs, request, default_size=10)
        self.assertEqual(list(items), [])
        self.assertEqual(meta["total"], 0)
        self.assertEqual(meta["total_pages"], 1)
        self.assertFalse(meta["has_next"])
        self.assertFalse(meta["has_previous"])


# ---------------------------------------------------------------------------
# Integration tests: GET /api/asistencias/?alumno=ID
# ---------------------------------------------------------------------------

@override_settings(SECURE_SSL_REDIRECT=False)
class AsistenciasPaginacionApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff = _make_user("staff_pag_asis", superuser=True)
        school, school_course = _setup_school()
        self.alumno = _make_alumno(school, school_course, legajo="LEG_ASIS_PAG")
        for i in range(80):
            Asistencia.objects.create(
                school=school,
                alumno=self.alumno,
                fecha=date(2025, 1, 1) + timedelta(days=i),

                tipo_asistencia="clases",
                presente=True,
            )
        self.client.force_authenticate(user=self.staff)
        self.url = f"/api/asistencias/?alumno={self.alumno.id}"

    def test_respuesta_incluye_campos_de_paginacion(self):
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        for campo in ("results", "page", "page_size", "total", "total_pages", "has_next", "has_previous"):
            self.assertIn(campo, data, f"Falta campo '{campo}' en la respuesta")

    def test_pagina_1_tiene_50_items_por_defecto(self):
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(len(data["results"]), DEFAULT_PAGE_SIZE)
        self.assertEqual(data["total"], 80)
        self.assertTrue(data["has_next"])
        self.assertFalse(data["has_previous"])

    def test_pagina_2_trae_el_resto(self):
        res = self.client.get(self.url + "&page=2")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(len(data["results"]), 30)
        self.assertFalse(data["has_next"])
        self.assertTrue(data["has_previous"])

    def test_items_no_se_solapan_entre_paginas(self):
        p1 = self.client.get(self.url + "&page=1").json()
        p2 = self.client.get(self.url + "&page=2").json()
        ids1 = {r["id"] for r in p1["results"]}
        ids2 = {r["id"] for r in p2["results"]}
        self.assertEqual(len(ids1 & ids2), 0)

    def test_page_size_custom(self):
        res = self.client.get(self.url + "&page=1&page_size=20")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(len(data["results"]), 20)
        self.assertEqual(data["total_pages"], 4)

    def test_sin_page_es_equivalente_a_page_1(self):
        sin_page = self.client.get(self.url).json()
        con_page = self.client.get(self.url + "&page=1").json()
        self.assertEqual(sin_page["page"], 1)
        self.assertEqual(
            [r["id"] for r in sin_page["results"]],
            [r["id"] for r in con_page["results"]],
        )

    def test_respuesta_incluye_datos_del_alumno(self):
        res = self.client.get(self.url)
        data = res.json()
        self.assertIn("alumno", data)
        self.assertEqual(data["alumno"]["id"], self.alumno.id)


# ---------------------------------------------------------------------------
# Integration tests: GET /api/sanciones/?alumno=ID
# ---------------------------------------------------------------------------

@override_settings(SECURE_SSL_REDIRECT=False)
class SancionesPaginacionApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff = _make_user("staff_pag_sanc", superuser=True)
        school, school_course = _setup_school()
        self.alumno = _make_alumno(school, school_course, legajo="LEG_SANC_PAG")
        for i in range(70):
            Sancion.objects.create(
                school=school,
                alumno=self.alumno,
                tipo="Amonestación",
                motivo=f"Motivo {i}",
                fecha=date(2025, 3, 1) + timedelta(days=i % 365),
                docente="Docente Test",
            )
        self.client.force_authenticate(user=self.staff)
        self.url = f"/api/sanciones/?alumno={self.alumno.id}"

    def test_respuesta_incluye_campos_de_paginacion(self):
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        for campo in ("results", "page", "page_size", "total", "total_pages", "has_next", "has_previous"):
            self.assertIn(campo, data, f"Falta campo '{campo}' en la respuesta")

    def test_pagina_1_tiene_50_items_por_defecto(self):
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(len(data["results"]), DEFAULT_PAGE_SIZE)
        self.assertEqual(data["total"], 70)
        self.assertTrue(data["has_next"])

    def test_pagina_2_trae_el_resto(self):
        res = self.client.get(self.url + "&page=2")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(len(data["results"]), 20)
        self.assertFalse(data["has_next"])
        self.assertTrue(data["has_previous"])

    def test_items_no_se_solapan_entre_paginas(self):
        p1 = self.client.get(self.url + "&page=1").json()
        p2 = self.client.get(self.url + "&page=2").json()
        ids1 = {r["id"] for r in p1["results"]}
        ids2 = {r["id"] for r in p2["results"]}
        self.assertEqual(len(ids1 & ids2), 0)

    def test_total_coincide_con_objetos_en_db(self):
        res = self.client.get(self.url)
        self.assertEqual(res.json()["total"], Sancion.objects.filter(alumno=self.alumno).count())

    def test_page_size_custom(self):
        res = self.client.get(self.url + "&page_size=10")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(len(data["results"]), 10)
        self.assertEqual(data["total_pages"], 7)

    def test_sin_page_es_equivalente_a_page_1(self):
        sin_page = self.client.get(self.url).json()
        con_page = self.client.get(self.url + "&page=1").json()
        self.assertEqual(
            [r["id"] for r in sin_page["results"]],
            [r["id"] for r in con_page["results"]],
        )
