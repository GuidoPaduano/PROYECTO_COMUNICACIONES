import os
import sqlite3

from django.contrib.auth import get_user_model
from django.http import FileResponse
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from tempfile import NamedTemporaryFile, TemporaryDirectory
from unittest.mock import patch


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

        with NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(b"backup")
            temp_file.flush()

        def fake_sqlite_backup_response():
            response = FileResponse(
                open(temp_file.name, "rb"),
                as_attachment=True,
                filename="global-backup-test.sqlite3",
                content_type="application/octet-stream",
            )
            response["X-Backup-Generated-By"] = "manual-platform-tool"
            response._resource_closers.append(lambda: os.remove(temp_file.name))
            return response, None

        with patch("calificaciones.api_backups._sqlite_backup_response", fake_sqlite_backup_response):
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

    def test_anonymous_user_cannot_generate_manual_backup(self):
        response = self.client.post("/api/admin/backups/manual/", {}, format="json")

        self.assertEqual(response.status_code, 401)

    @override_settings(
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.oracle",
                "NAME": "unsupported",
            }
        }
    )
    def test_unsupported_database_engine_is_rejected(self):
        admin = _make_user("unsupported_backup_admin", is_superuser=True)
        self.client.force_authenticate(user=admin)

        response = self.client.post("/api/admin/backups/manual/", {}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Motor de base no soportado para backup manual.")


class SqliteBackupIntegrityTests(TestCase):
    def test_backup_is_restorable_and_contains_committed_wal_data(self):
        from calificaciones.api_backups import _sqlite_backup_response

        with TemporaryDirectory() as temp_dir:
            source_path = os.path.join(temp_dir, "source.sqlite3")
            restored_path = os.path.join(temp_dir, "restored.sqlite3")
            connection = sqlite3.connect(source_path)
            try:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA wal_autocheckpoint=0")
                connection.execute("CREATE TABLE qa_restore (id INTEGER PRIMARY KEY, value TEXT)")
                connection.commit()
                connection.execute("INSERT INTO qa_restore(value) VALUES (?)", ("dato confirmado",))
                connection.commit()

                with override_settings(
                    DATABASES={
                        "default": {
                            "ENGINE": "django.db.backends.sqlite3",
                            "NAME": source_path,
                        }
                    }
                ):
                    response, error = _sqlite_backup_response()
                    self.assertIsNone(error)
                    with open(restored_path, "wb") as restored:
                        for chunk in response.streaming_content:
                            restored.write(chunk)
                    response.close()

                restored = sqlite3.connect(restored_path)
                try:
                    self.assertEqual(restored.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                    self.assertEqual(
                        restored.execute("SELECT value FROM qa_restore").fetchone()[0],
                        "dato confirmado",
                    )
                finally:
                    restored.close()
            finally:
                connection.close()

    def test_missing_sqlite_database_returns_controlled_error(self):
        from calificaciones.api_backups import _sqlite_backup_response

        with TemporaryDirectory() as temp_dir:
            missing_path = os.path.join(temp_dir, "missing.sqlite3")
            with override_settings(
                DATABASES={
                    "default": {
                        "ENGINE": "django.db.backends.sqlite3",
                        "NAME": missing_path,
                    }
                }
            ):
                response, error = _sqlite_backup_response()

        self.assertIsNone(response)
        self.assertEqual(error.status_code, 400)
        self.assertEqual(error.data["detail"], "La base SQLite local no existe.")


class PostgresBackupFailureTests(TestCase):
    @override_settings(
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": "qa",
            }
        }
    )
    def test_missing_database_url_returns_controlled_error(self):
        from calificaciones.api_backups import _postgres_backup_response

        with patch.dict(os.environ, {}, clear=True):
            response, error = _postgres_backup_response()

        self.assertIsNone(response)
        self.assertEqual(error.status_code, 500)
        self.assertEqual(error.data["detail"], "DATABASE_URL no está configurada.")

    @override_settings(
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": "qa",
            }
        }
    )
    def test_missing_pg_dump_returns_controlled_error(self):
        from calificaciones.api_backups import _postgres_backup_response

        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@db/qa"}, clear=True):
            with patch("calificaciones.api_backups.shutil.which", return_value=None):
                response, error = _postgres_backup_response()

        self.assertIsNone(response)
        self.assertEqual(error.status_code, 500)
        self.assertEqual(error.data["detail"], "pg_dump no está disponible en el contenedor.")
