from ._views import (
    admin_create_school_course,
    admin_create_school,
    admin_school_courses,
    admin_school_admins,
    admin_school_deletion_job,
    admin_upload_school_logo,
    admin_update_school_course,
    admin_update_school,
    admin_update_school_admins,
    public_school_branding,
    public_school_directory,
)
from ._helpers import (  # noqa: F401 — usado por tests
    _run_school_deletion_job,
    _schedule_school_deletion_job,
)

__all__ = [
    "admin_create_school_course",
    "admin_create_school",
    "admin_school_courses",
    "admin_school_admins",
    "admin_school_deletion_job",
    "admin_upload_school_logo",
    "admin_update_school_course",
    "admin_update_school",
    "admin_update_school_admins",
    "public_school_branding",
    "public_school_directory",
]
