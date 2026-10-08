from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..api_padres import invalidate_mis_hijos_cache
from ..jwt_auth import CookieJWTAuthentication as JWTAuthentication
from ..models import Alumno, SchoolCourse
from ..schools import school_to_dict
from ._helpers import _contains_digit, _require_school_admin, _resolve_requested_admin_school, _serialize_directory_student


def _student_data(student):
    course = student.school_course
    return {
        'id': student.id,
        'nombre': student.nombre,
        'apellido': student.apellido,
        'id_alumno': student.id_alumno,
        'es_ppi': student.es_ppi,
        'school_course_id': course.id,
        'school_course_name': course.name or course.code,
        'nivel': course.nivel,
    }


def _admin_school(request):
    denied = _require_school_admin(request)
    if denied is not None:
        return None, denied
    return _resolve_requested_admin_school(request)


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def admin_students(request):
    school, denied = _admin_school(request)
    if denied is not None:
        return denied
    students = Alumno.objects.filter(school=school).select_related('school_course')
    # Match each word independently to support both name orders.
    for term in str(request.GET.get('q') or '').strip().split():
        students = students.filter(Q(nombre__icontains=term) | Q(apellido__icontains=term) | Q(id_alumno__icontains=term))
    try:
        page = max(1, int(request.GET.get('page', 1)))
    except (TypeError, ValueError):
        return Response({'detail': 'Página inválida.'}, status=400)
    count = students.count()
    rows = students.order_by('apellido', 'nombre', 'id')[(page - 1) * 50:page * 50]
    courses = SchoolCourse.objects.filter(school=school).order_by('sort_order', 'name', 'id')
    return Response({
        'school': school_to_dict(school),
        'students': [_student_data(student) for student in rows],
        'count': count, 'page': page, 'has_next': page * 50 < count,
        'courses': [{'id': c.id, 'name': c.name or c.code, 'nivel': c.nivel, 'is_active': c.is_active} for c in courses],
    })


@api_view(['GET', 'PATCH'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def admin_student_update(request, student_id):
    school, denied = _admin_school(request)
    if denied is not None:
        return denied
    if request.method == 'GET':
        student = Alumno.objects.filter(pk=student_id, school=school).select_related('school_course', 'usuario', 'padre').first()
        if student is None:
            return Response({'detail': 'Alumno no encontrado en el colegio activo.'}, status=404)
        courses = SchoolCourse.objects.filter(school=school).order_by('sort_order', 'name', 'id')
        membership = dict(school.user_memberships.values_list('user_id', 'is_active'))
        return Response({
            'student': {**_serialize_directory_student(student, membership_active=membership), **_student_data(student)},
            'courses': [{'id': c.id, 'name': c.name or c.code, 'nivel': c.nivel, 'is_active': c.is_active} for c in courses],
        })
    allowed = {'nombre', 'apellido', 'id_alumno', 'es_ppi', 'school_course_id'}
    data = request.data
    if not isinstance(data, dict) or not data or set(data) - allowed:
        return Response({'detail': 'Enviá solo los datos del alumno, PPI y curso.'}, status=400)
    try:
        with transaction.atomic():
            student = Alumno.objects.select_for_update().filter(pk=student_id, school=school).first()
            if student is None:
                return Response({'detail': 'Alumno no encontrado en el colegio activo.'}, status=404)
            for field, limit in [('nombre', 100), ('apellido', 100), ('id_alumno', 20)]:
                if field not in data:
                    continue
                value = data[field]
                if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
                    return Response({'detail': f'{field}: ingresá un texto de entre 1 y {limit} caracteres.'}, status=400)
                if field != 'id_alumno' and _contains_digit(value):
                    return Response({'detail': 'El nombre y el apellido no pueden contener números.'}, status=400)
                setattr(student, field, value.strip())
            if 'es_ppi' in data:
                if not isinstance(data['es_ppi'], bool):
                    return Response({'detail': 'PPI debe ser true o false.'}, status=400)
                student.es_ppi = data['es_ppi']
            if 'school_course_id' in data:
                course_id = data['school_course_id']
                if type(course_id) is not int:
                    return Response({'detail': 'Seleccioná un curso válido.'}, status=400)
                course = SchoolCourse.objects.filter(pk=course_id, school=school).first()
                if course is None or (not course.is_active and course.id != student.school_course_id):
                    return Response({'detail': 'Seleccioná un curso activo del colegio.'}, status=400)
                student.school_course = course
                student.curso = course.code
                student.nivel = course.nivel
            fields = set(data)
            if 'school_course_id' in fields:
                fields.remove('school_course_id')
                fields.update(['school_course', 'curso', 'nivel'])
            student.save(update_fields=fields)
            transaction.on_commit(lambda: invalidate_mis_hijos_cache(user_id=student.padre_id, school_id=school.id))
            result = _student_data(student)
    except ValidationError as exc:
        return Response({'detail': ' '.join(exc.messages)}, status=400)
    except IntegrityError:
        return Response({'detail': 'Ya existe un alumno con ese legajo en el colegio.'}, status=400)
    return Response({'student': result, 'detail': 'Alumno actualizado correctamente.'})
