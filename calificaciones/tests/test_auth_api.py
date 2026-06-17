from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import TestCase, override_settings

from calificaciones.models import Alumno, School, SchoolCourse


TEST_REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "calificaciones.jwt_auth.CookieJWTAuthentication",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "1000/min",
        "user": "1000/min",
    },
}


@override_settings(SECURE_SSL_REDIRECT=False, REST_FRAMEWORK=TEST_REST_FRAMEWORK)
class AuthApiContractTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.defaults["HTTP_ACCEPT"] = "application/json"
        self.password = "test1234"
        self.user = get_user_model().objects.create_user(
            username="auth_contract_user",
            password=self.password,
            is_superuser=True,
            is_staff=True,
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

    def test_logout_accepts_slash_and_no_slash_paths(self):
        for path in ["/api/auth/logout/", "/api/auth/logout"]:
            with self.subTest(path=path):
                response = self.client.post(path)

                self.assertEqual(response.status_code, 204)
                self.assertEqual(response.content, b"")

    def test_refresh_verify_and_blacklist_without_cookies_reject_and_clear_auth_cookies(self):
        for path in ["/api/token/refresh/", "/api/token/blacklist/"]:
            with self.subTest(path=path):
                response = self.client.post(path, data={}, content_type="application/json")

                self.assertEqual(response.status_code, 401)
                self.assertIn("access_token", response.cookies)
                self.assertIn("refresh_token", response.cookies)
                self.assertEqual(response.cookies["access_token"].value, "")
                self.assertEqual(response.cookies["refresh_token"].value, "")

        verify = self.client.post("/api/token/verify/", data={}, content_type="application/json")

        self.assertEqual(verify.status_code, 401)
        self.assertIn("detail", verify.json())

    def test_blacklisted_refresh_token_cannot_be_used_again(self):
        obtain = self.client.post(
            "/api/token/",
            data={"username": self.user.username, "password": self.password},
            content_type="application/json",
        )
        self.assertEqual(obtain.status_code, 200)

        blacklist = self.client.post("/api/token/blacklist/", data={}, content_type="application/json")
        self.assertEqual(blacklist.status_code, 204)

        refresh = self.client.post("/api/token/refresh/", data={}, content_type="application/json")

        self.assertEqual(refresh.status_code, 401)
        self.assertIn("access_token", refresh.cookies)
        self.assertEqual(refresh.cookies["access_token"].value, "")

    def test_token_login_rejects_regular_user_in_other_school_context(self):
        school_a = School.objects.create(name="Auth School A", short_name="Auth A", slug="auth-school-a")
        school_b = School.objects.create(name="Auth School B", short_name="Auth B", slug="auth-school-b")
        course_a = SchoolCourse.objects.create(school=school_a, code="1A", name="1A Auth")
        user = get_user_model().objects.create_user(username="auth_student_a", password=self.password)
        group, _ = Group.objects.get_or_create(name="Alumnos")
        user.groups.add(group)
        Alumno.objects.create(
            school=school_a,
            school_course=course_a,
            nombre="Ana",
            apellido="Auth",
            id_alumno="AUTH-A-001",
            usuario=user,
        )

        response = self.client.post(
            "/api/token/",
            data={"username": user.username, "password": self.password},
            content_type="application/json",
            HTTP_X_SCHOOL=school_b.slug,
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "El usuario no pertenece al colegio seleccionado.")
        self.assertIn("access_token", response.cookies)
        self.assertEqual(response.cookies["access_token"].value, "")

    def test_whoami_rejects_regular_user_with_other_school_header_from_cookie_auth(self):
        school_a = School.objects.create(name="Whoami School A", short_name="Whoami A", slug="whoami-school-a")
        school_b = School.objects.create(name="Whoami School B", short_name="Whoami B", slug="whoami-school-b")
        course_a = SchoolCourse.objects.create(school=school_a, code="1A", name="1A Whoami")
        user = get_user_model().objects.create_user(username="whoami_student_a", password=self.password)
        group, _ = Group.objects.get_or_create(name="Alumnos")
        user.groups.add(group)
        Alumno.objects.create(
            school=school_a,
            school_course=course_a,
            nombre="Wanda",
            apellido="Auth",
            id_alumno="AUTH-W-001",
            usuario=user,
        )
        obtain = self.client.post(
            "/api/token/",
            data={"username": user.username, "password": self.password},
            content_type="application/json",
            HTTP_X_SCHOOL=school_a.slug,
        )
        self.assertEqual(obtain.status_code, 200)

        response = self.client.get("/api/auth/whoami/", HTTP_X_SCHOOL=school_b.slug)

        self.assertEqual(response.status_code, 403)
        self.assertIn("detail", response.json())

    @override_settings(
        JWT_COOKIE_SECURE=True,
        JWT_COOKIE_SAMESITE="Strict",
        JWT_COOKIE_PATH="/",
        JWT_ACCESS_COOKIE_AGE=900,
        JWT_REFRESH_COOKIE_AGE=86400,
    )
    def test_auth_cookies_are_http_only_secure_and_scoped(self):
        response = self.client.post(
            "/api/token/",
            data={"username": self.user.username, "password": self.password},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {})
        for cookie_name, max_age in (("access_token", 900), ("refresh_token", 86400)):
            cookie = response.cookies[cookie_name]
            self.assertTrue(cookie["httponly"])
            self.assertTrue(cookie["secure"])
            self.assertEqual(cookie["samesite"], "Strict")
            self.assertEqual(cookie["path"], "/")
            self.assertEqual(cookie["max-age"], max_age)

    @override_settings(
        REST_FRAMEWORK={
            "DEFAULT_AUTHENTICATION_CLASSES": (
                "calificaciones.jwt_auth.CookieJWTAuthentication",
            ),
            "DEFAULT_THROTTLE_RATES": {
                "login": "2/min",
            },
        }
    )
    def test_login_throttle_blocks_repeated_password_attempts(self):
        cache.clear()
        payload = {"username": self.user.username, "password": "incorrecta"}

        first = self.client.post("/api/token/", payload, content_type="application/json")
        second = self.client.post("/api/token/", payload, content_type="application/json")
        blocked = self.client.post("/api/token/", payload, content_type="application/json")

        self.assertEqual(first.status_code, 401)
        self.assertEqual(second.status_code, 401)
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("detail", blocked.json())

        other_user = self.client.post(
            "/api/token/",
            {"username": "otra_cuenta", "password": "incorrecta"},
            content_type="application/json",
        )
        self.assertEqual(other_user.status_code, 401)
