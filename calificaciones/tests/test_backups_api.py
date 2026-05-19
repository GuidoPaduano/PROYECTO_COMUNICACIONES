from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient


def _make_user(username: str, *, is_superuser: bool = False):
    return get_user_model().objects.create_user(
        username=username,
        password="test1234",
        is_superuser=is_superuser,
        is_staff=is_superuser,
    )


@override_settings(SECURE_SSL_REDIRECT=False)
class ManualPlatformBackupApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_superuser_can_download_manual_backup(self):
        admin = _make_user("backup_admin", is_superuser=True)
        self.client.force_authenticate(user=admin)

        response = self.client.post("/api/admin/backups/manual/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertIn("global-backup-", response["Content-Disposition"])
        self.assertEqual(response["X-Backup-Generated-By"], "manual-platform-tool")
        first_chunk = b"".join(response.streaming_content)
        self.assertGreater(len(first_chunk), 0)

    def test_non_superuser_cannot_generate_manual_backup(self):
        user = _make_user("backup_user", is_superuser=False)
        self.client.force_authenticate(user=user)

        response = self.client.post("/api/admin/backups/manual/", {}, format="json")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "No autorizado.")
