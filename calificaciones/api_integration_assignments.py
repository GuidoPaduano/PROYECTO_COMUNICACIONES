from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .api_admin_staff._helpers import _require_school_admin, _resolve_requested_admin_school
from .api_ppi_documents import _school
from .integration_access import integration_can_access_school
from .jwt_auth import CookieJWTAuthentication
from .models import Alumno, IntegrationStudentAssignment


def _eligible_teachers(school):
    return get_user_model().objects.filter(
        is_active=True, groups__name='Integracion',
        school_memberships__school=school, school_memberships__is_active=True,
    ).distinct()


def _student_data(student):
    return {'id': student.id, 'nombre': student.nombre, 'apellido': student.apellido,
            'legajo': student.id_alumno, 'curso': student.school_course.name,
            'school_course_id': student.school_course_id}


@api_view(['GET'])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated])
def integration_assignment_overview(request):
    denied = _require_school_admin(request)
    if denied is not None:
        return denied
    school, denied = _resolve_requested_admin_school(request)
    if denied is not None:
        return denied
    assignments = IntegrationStudentAssignment.objects.filter(school=school, alumno__school=school)
    by_student = {}
    for student_id, teacher_id in assignments.values_list('alumno_id', 'maestra_id'):
        by_student.setdefault(student_id, []).append(teacher_id)
    eligible_ids = set(_eligible_teachers(school).values_list('id', flat=True))
    teachers = get_user_model().objects.filter(
        Q(groups__name='Integracion', school_memberships__school=school)
        | Q(id__in=assignments.values('maestra_id'))
    ).distinct().order_by('last_name', 'first_name', 'username')
    students = Alumno.objects.filter(school=school, es_ppi=True).select_related('school_course').order_by('apellido', 'nombre', 'id')
    return Response({
        'alumnos': [{**_student_data(a), 'maestra_ids': by_student.get(a.id, [])} for a in students],
        'maestras': [{'id': u.id, 'nombre': u.get_full_name() or u.username, 'email': u.email,
                     'disponible': u.id in eligible_ids} for u in teachers],
    })


@api_view(['PATCH'])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated])
def integration_assignment_update(request, alumno_id):
    denied = _require_school_admin(request)
    if denied is not None:
        return denied
    school, denied = _resolve_requested_admin_school(request)
    if denied is not None:
        return denied
    data = request.data
    ids = data.get('maestra_ids') if isinstance(data, dict) else None
    if not isinstance(ids, list) or any(type(pk) is not int or pk <= 0 for pk in ids):
        return Response({'detail': 'Enviá una lista válida de maestras.'}, status=400)
    selected = set(ids)
    if selected != set(_eligible_teachers(school).filter(id__in=selected).values_list('id', flat=True)):
        return Response({'detail': 'Seleccioná maestras de integración activas del colegio. Quitá de la selección a quienes ya no están disponibles.'}, status=400)
    with transaction.atomic():
        student = Alumno.objects.select_for_update().filter(pk=alumno_id, school=school, es_ppi=True).first()
        if student is None:
            return Response({'detail': 'Alumno PPI no encontrado en este colegio.'}, status=404)
        current = IntegrationStudentAssignment.objects.filter(school=school, alumno=student)
        current.exclude(maestra_id__in=selected).delete()
        for pk in selected:
            IntegrationStudentAssignment.objects.get_or_create(school=school, alumno=student, maestra_id=pk)
    return Response({'detail': 'Asignación del alumno guardada.', 'alumno_id': student.id, 'maestra_ids': sorted(selected)})


@api_view(['GET'])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated])
def integration_students(request):
    school, denied = _school(request)
    if denied is not None:
        return denied
    if not integration_can_access_school(request.user, school):
        return Response({'detail': 'No autorizado para integración en este colegio.'}, status=403)
    students = Alumno.objects.filter(
        school=school, es_ppi=True, integration_assignments__school=school,
        integration_assignments__maestra=request.user,
    ).select_related('school_course').distinct().order_by('apellido', 'nombre', 'id')
    return Response({'alumnos': [_student_data(a) for a in students]})
