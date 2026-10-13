from .models import IntegrationStudentAssignment
from .models_preceptores import SchoolMembership
from .user_groups import get_user_group_names


def integration_can_access_school(user, school):
    return bool(
        school is not None
        and getattr(user, 'is_active', False)
        and 'Integracion' in get_user_group_names(user)
        and SchoolMembership.objects.filter(user=user, school=school, is_active=True).exists()
    )


def integration_can_access_student(user, alumno):
    return bool(
        alumno.es_ppi and integration_can_access_school(user, alumno.school)
        and IntegrationStudentAssignment.objects.filter(maestra=user, alumno=alumno, school_id=alumno.school_id).exists()
    )
