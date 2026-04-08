from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings


@override_settings(SECURE_SSL_REDIRECT=False)
class AuthApiContractTests(TestCase):
    def setUp(self):
        self.client.defaults["HTTP_ACCEPT"] = "application/json"
        self.password = "test1234"
        self.user = get_user_model().objects.create_user(
            username="auth_contract_user",
            password=self.password,
        )

    def test_token_obtain_refresh_verify_and_blacklist_use_minimal_success_contracts(self):
        obtain = self.client.post(
            "/api/token/",
            data={"username": self.user.username, "password": self.password},
            content_type="application/json",
        )

        self.assertEqual(obtain.status_code, 200)
        self.assertEqual(obtain.json(), {})
        self.assertIn("access_token", obtain.cookies)
        self.assertIn("refresh_token", obtain.cookies)

        verify = self.client.post(
            "/api/token/verify/",
            data={},
            content_type="application/json",
        )

        self.assertEqual(verify.status_code, 204)
        self.assertEqual(verify.content, b"")

        refresh = self.client.post(
            "/api/token/refresh/",
            data={},
            content_type="application/json",
        )

        self.assertEqual(refresh.status_code, 200)
        self.assertEqual(refresh.json(), {})
        self.assertIn("access_token", refresh.cookies)

        blacklist = self.client.post(
            "/api/token/blacklist/",
            data={},
            content_type="application/json",
        )

        self.assertEqual(blacklist.status_code, 204)
        self.assertEqual(blacklist.content, b"")
        self.assertIn("access_token", blacklist.cookies)
        self.assertIn("refresh_token", blacklist.cookies)
        self.assertEqual(blacklist.cookies["access_token"].value, "")
        self.assertEqual(blacklist.cookies["refresh_token"].value, "")
