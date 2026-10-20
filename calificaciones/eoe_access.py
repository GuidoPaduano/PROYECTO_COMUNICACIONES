from .models_preceptores import SchoolMembership
from .user_groups import get_user_group_names


def eoe_can_access_school(user, school):
    return bool(
        school is not None
        and getattr(user, 'is_active', False)
        and 'EOE' in get_user_group_names(user)
        and SchoolMembership.objects.filter(user=user, school=school, is_active=True).exists()
    )


def eoe_can_view_student(user, alumno):
    """EOE can read PPI student records in schools where it has an active membership."""
    return bool(
        alumno is not None
        and getattr(alumno, 'es_ppi', False)
        and eoe_can_access_school(user, getattr(alumno, 'school', None))
    )
