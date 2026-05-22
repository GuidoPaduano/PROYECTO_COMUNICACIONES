import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse

from django.conf import settings
from django.http import FileResponse
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


def _require_platform_admin(user):
    return bool(getattr(user, "is_authenticated", False) and getattr(user, "is_superuser", False))


def _safe_db_name_from_url(database_url: str) -> str:
    parsed = urlparse(database_url or "")
    raw_name = unquote(parsed.path.lstrip("/")).strip() or "database"
    normalized = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in raw_name)
    return normalized[:80] or "database"


def _build_backup_filename(*, extension: str, database_name: str) -> str:
    timestamp = timezone.now().strftime("%Y%m%d-%H%M%S")
    return f"global-backup-{database_name}-{timestamp}.{extension}"


def _cleanup_temp_path(file_path: str, temp_dir: str):
    try:
        os.remove(file_path)
    except FileNotFoundError:
        pass
    except Exception:
        pass

    try:
        os.rmdir(temp_dir)
    except OSError:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass


def _sqlite_backup_response():
    db_name = Path(settings.DATABASES["default"].get("NAME") or "").resolve()
    if not db_name.exists():
        return None, Response({"detail": "La base SQLite local no existe."}, status=400)

    temp_dir = tempfile.mkdtemp(prefix="platform-backup-")
    backup_name = _build_backup_filename(extension="sqlite3", database_name=db_name.stem or "sqlite")
    backup_path = os.path.join(temp_dir, backup_name)
    shutil.copy2(db_name, backup_path)

    response = FileResponse(
        open(backup_path, "rb"),
        as_attachment=True,
        filename=backup_name,
        content_type="application/octet-stream",
    )
    response["X-Backup-Engine"] = "sqlite"
    response["X-Backup-Generated-By"] = "manual-platform-tool"
    response._resource_closers.append(lambda: _cleanup_temp_path(backup_path, temp_dir))
    return response, None


def _postgres_backup_response():
    database_url = (os.environ.get("DATABASE_URL") or "").strip()
    if not database_url:
        return None, Response({"detail": "DATABASE_URL no está configurada."}, status=500)

    if shutil.which("pg_dump") is None:
        return None, Response({"detail": "pg_dump no está disponible en el contenedor."}, status=500)

    database_name = _safe_db_name_from_url(database_url)
    temp_dir = tempfile.mkdtemp(prefix="platform-backup-")
    backup_name = _build_backup_filename(extension="dump", database_name=database_name)
    backup_path = os.path.join(temp_dir, backup_name)

    command = [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        f"--file={backup_path}",
        database_url,
    ]

    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
    except subprocess.CalledProcessError as exc:
        _cleanup_temp_path(backup_path, temp_dir)
        stderr = (exc.stderr or "").strip()
        detail = "No se pudo generar el backup de PostgreSQL."
        if stderr:
            detail = f"{detail} {stderr[:300]}"
        return None, Response({"detail": detail}, status=500)

    response = FileResponse(
        open(backup_path, "rb"),
        as_attachment=True,
        filename=backup_name,
        content_type="application/octet-stream",
    )
    response["X-Backup-Engine"] = "postgres"
    response["X-Backup-Generated-By"] = "manual-platform-tool"
    response._resource_closers.append(lambda: _cleanup_temp_path(backup_path, temp_dir))
    return response, None


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def admin_manual_platform_backup(request):
    if not _require_platform_admin(getattr(request, "user", None)):
        return Response({"detail": "No autorizado."}, status=403)

    engine = settings.DATABASES["default"].get("ENGINE", "")
    if "sqlite" in engine:
        response, error = _sqlite_backup_response()
    elif "postgresql" in engine or "postgres" in engine:
        response, error = _postgres_backup_response()
    else:
        return Response({"detail": "Motor de base no soportado para backup manual."}, status=400)

    if error is not None:
        return error
    return response
