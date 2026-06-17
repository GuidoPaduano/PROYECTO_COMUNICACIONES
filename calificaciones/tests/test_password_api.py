from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.test import TestCase, override_settings
from django.utils.http import urlsafe_base64_encode
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

from unittest.mock import patch


TEST_REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "calificaciones.jwt_auth.CookieJWTAuthentication",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "1000/min",
        "user": "1000/min",
    },
}


@override_settings(
    SECURE_SSL_REDIRECT=False,
    FRONTEND_BASE_URL="https://app.test",
    PASSWORD_RESET_PATH="/reset-password",
    REST_FRAMEWORK=TEST_REST_FRAMEWORK,
)
class PasswordResetApiTests(TestCase):
    def setUp(self):
        self.client.defaults["HTTP_ACCEPT"] = "application/json"
        self.client.defaults["REMOTE_ADDR"] = f"10.10.1.{abs(hash(self._testMethodName)) % 200 + 1}"
        self.password = "OldPassword123!"
        self.user = get_user_model().objects.create_user(
            username="password_reset_user",
            email="reset@example.com",
            password=self.password,
            is_superuser=True,
            is_staff=True,
        )

    def test_password_reset_request_uses_generic_response_for_unknown_email(self):
        with patch("calificaciones.api_password_reset.send_resend_email") as send_email:
            response = self.client.post(
                "/api/auth/password-reset/",
                data={"email": "missing@example.com"},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Si el correo existe", response.json()["detail"])
        send_email.assert_not_called()

    def test_password_reset_routes_accept_posts_without_trailing_slash(self):
        with patch("calificaciones.api_password_reset.send_resend_email") as send_email:
            request_response = self.client.post(
                "/api/auth/password-reset",
                data={"email": "missing@example.com"},
                content_type="application/json",
            )

        self.assertEqual(request_response.status_code, 200)
        send_email.assert_not_called()

        confirm_response = self.client.post(
            "/api/auth/password-reset/confirm",
            data={"uid": "bad-uid", "token": "bad-token", "password": "NewPassword123!"},
            content_type="application/json",
        )
        self.assertEqual(confirm_response.status_code, 400)
        self.assertIn("Link", confirm_response.json()["detail"])

    def test_password_reset_request_sends_reset_link_for_existing_email(self):
        with patch("calificaciones.api_password_reset.send_resend_email") as send_email:
            response = self.client.post(
                "/api/auth/password-reset/",
                data={"correo": "RESET@example.com"},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        send_email.assert_called_once()
        kwargs = send_email.call_args.kwargs
        self.assertEqual(kwargs["to_email"], "reset@example.com")
        self.assertIn("https://app.test/reset-password?uid=", kwargs["text"])
        self.assertIn("&token=", kwargs["text"])

    @override_settings(FRONTEND_BASE_URL="")
    @patch.dict("os.environ", {"FRONTEND_BASE_URL": ""})
    def test_password_reset_request_for_existing_user_requires_frontend_base_url(self):
        with patch("calificaciones.api_password_reset.send_resend_email") as send_email:
            response = self.client.post(
                "/api/auth/password-reset/",
                data={"email": self.user.email},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 500)
        self.assertIn("frontend", response.json()["detail"].lower())
        send_email.assert_not_called()

    def test_password_reset_confirm_rejects_missing_or_invalid_token(self):
        missing = self.client.post(
            "/api/auth/password-reset/confirm/",
            data={"uid": "", "token": "", "password": "NewPassword123!"},
            content_type="application/json",
        )
        self.assertEqual(missing.status_code, 400)

        invalid = self.client.post(
            "/api/auth/password-reset/confirm/",
            data={"uid": "bad-uid", "token": "bad-token", "password": "NewPassword123!"},
            content_type="application/json",
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("Link", invalid.json()["detail"])

    def test_password_reset_confirm_updates_password_and_rejects_token_reuse(self):
        uid = urlsafe_base64_encode(str(self.user.pk).encode("utf-8"))
        token = default_token_generator.make_token(self.user)

        response = self.client.post(
            "/api/auth/password-reset/confirm/",
            data={"uid": uid, "token": token, "password": "NewPassword123!"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPassword123!"))

        reused = self.client.post(
            "/api/auth/password-reset/confirm/",
            data={"uid": uid, "token": token, "password": "AnotherPassword123!"},
            content_type="application/json",
        )
        self.assertEqual(reused.status_code, 400)

    @override_settings(
        AUTH_PASSWORD_VALIDATORS=[
            {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
        ]
    )
    def test_password_reset_confirm_applies_password_validation(self):
        uid = urlsafe_base64_encode(str(self.user.pk).encode("utf-8"))
        token = default_token_generator.make_token(self.user)

        response = self.client.post(
            "/api/auth/password-reset/confirm/",
            data={"uid": uid, "token": token, "password": "short"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIsInstance(response.json()["detail"], list)

    def test_password_reset_confirm_blacklists_existing_refresh_tokens(self):
        login = self.client.post(
            "/api/token/",
            data={"username": self.user.username, "password": self.password},
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200)
        uid = urlsafe_base64_encode(str(self.user.pk).encode("utf-8"))
        token = default_token_generator.make_token(self.user)

        response = self.client.post(
            "/api/auth/password-reset/confirm/",
            data={"uid": uid, "token": token, "password": "NewPassword123!"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(BlacklistedToken.objects.filter(token__user=self.user).exists())
        refresh = self.client.post("/api/token/refresh/", data={}, content_type="application/json")
        self.assertEqual(refresh.status_code, 401)


@override_settings(SECURE_SSL_REDIRECT=False, REST_FRAMEWORK=TEST_REST_FRAMEWORK)
class PasswordChangeApiTests(TestCase):
    def setUp(self):
        self.client.defaults["HTTP_ACCEPT"] = "application/json"
        self.client.defaults["REMOTE_ADDR"] = f"10.10.2.{abs(hash(self._testMethodName)) % 200 + 1}"
        self.password = "CurrentPassword123!"
        self.user = get_user_model().objects.create_user(
            username="password_change_user",
            email="change@example.com",
            password=self.password,
            is_superuser=True,
            is_staff=True,
        )

    def _login(self):
        response = self.client.post(
            "/api/token/",
            data={"username": self.user.username, "password": self.password},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

    def test_password_change_requires_authenticated_user(self):
        response = self.client.post(
            "/api/auth/password-change/",
            data={"current_password": self.password, "new_password": "ChangedPassword123!"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)

    def test_password_change_rejects_missing_or_wrong_current_password(self):
        self._login()

        missing = self.client.post(
            "/api/auth/password-change/",
            data={"current_password": "", "new_password": "ChangedPassword123!"},
            content_type="application/json",
        )
        self.assertEqual(missing.status_code, 400)

        wrong = self.client.post(
            "/api/auth/password-change/",
            data={"current_password": "wrong", "new_password": "ChangedPassword123!"},
            content_type="application/json",
        )
        self.assertEqual(wrong.status_code, 400)
        self.assertIn("actual", wrong.json()["detail"])

    @override_settings(
        AUTH_PASSWORD_VALIDATORS=[
            {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
        ]
    )
    def test_password_change_applies_password_validation(self):
        self._login()

        response = self.client.post(
            "/api/auth/password-change/",
            data={"current_password": self.password, "new_password": "short"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIsInstance(response.json()["detail"], list)

    def test_password_change_updates_password_and_blacklists_existing_refresh_tokens(self):
        self._login()

        response = self.client.post(
            "/api/auth/password-change/",
            data={"current_password": self.password, "new_password": "ChangedPassword123!"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("ChangedPassword123!"))
        self.assertTrue(BlacklistedToken.objects.filter(token__user=self.user).exists())

        refresh = self.client.post("/api/token/refresh/", data={}, content_type="application/json")
        self.assertEqual(refresh.status_code, 401)
