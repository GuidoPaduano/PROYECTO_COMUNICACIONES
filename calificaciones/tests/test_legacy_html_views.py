from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings


def _make_user(username: str, *, is_superuser: bool = False):
    User = get_user_model()
    return User.objects.create_user(
        username=username,
        password="test1234",
        is_superuser=is_superuser,
        is_staff=is_superuser,
    )


LEGACY_URLS = [
    "/agregar_nota/",
    "/ver_notas/",
    "/agregar_nota_masiva/",
    "/enviar_mensaje/",
    "/enviar_comunicado/",
    "/ver_mensajes/",
    "/historial/profesor/LEGAJO001/",
    "/historial/padre/",
    "/pasar_asistencia/",
    "/perfil_alumno/LEGAJO001/",
    "/eventos/",
    "/eventos/crear/",
    "/eventos/editar/1/",
    "/eventos/eliminar/1/",
    "/mi_perfil/",
]


@override_settings(SECURE_SSL_REDIRECT=False)
class LegacyHtmlViewsReturn410Tests(TestCase):
    """Las vistas HTML legacy fueron reemplazadas por el frontend Next.js y devuelven 410."""

    def setUp(self):
        self.client = Client()
        self.user = _make_user("legacy_test_user", is_superuser=True)
        self.client.force_login(self.user)

    def test_legacy_urls_return_410(self):
        for url in LEGACY_URLS:
            with self.subTest(url=url):
                res = self.client.get(url)
                self.assertEqual(
                    res.status_code,
                    410,
                    f"{url} debería devolver 410 Gone, devolvió {res.status_code}",
                )
