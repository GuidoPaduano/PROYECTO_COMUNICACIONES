import io
import os

from django.db import transaction
from django.http import FileResponse
from rest_framework.decorators import api_view, authentication_classes, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .jwt_auth import CookieJWTAuthentication
from .models import Alumno, PpiDocument
from .models_preceptores import SchoolAdmin
from .schools import get_request_school, get_requested_school_identifier, get_school_by_identifier
from .user_groups import get_user_group_names
from .views._acceso import _preceptor_can_access_alumno, _profesor_can_access_alumno

MAX_PDF_BYTES = 20 * 1024 * 1024


def _access(request, alumno_id):
    school = get_request_school(request)
    if school is None:
        return None, False, Response({'detail': 'Seleccioná un colegio.'}, status=400)
    requested = get_requested_school_identifier(request)
    if requested:
        requested_school = get_school_by_identifier(requested)
        if requested_school is None or requested_school.id != school.id:
            return None, False, Response({'detail': 'No autorizado para el colegio solicitado.'}, status=403)
    alumno = Alumno.objects.filter(pk=alumno_id, school=school).select_related('school_course', 'school').first()
    if alumno is None:
        return None, False, Response({'detail': 'Alumno no encontrado.'}, status=404)
    user = request.user
    groups = set(get_user_group_names(user))
    admin = user.is_superuser or ('Administradores' in groups and SchoolAdmin.objects.filter(admin=user, school=school).exists())
    institutional = admin or 'Directivos' in groups
    preceptor = 'Preceptores' in groups and _preceptor_can_access_alumno(user, alumno)
    teacher = 'Profesores' in groups and _profesor_can_access_alumno(user, alumno)
    if not (institutional or preceptor or teacher):
        return None, False, Response({'detail': 'No autorizado para este alumno.'}, status=403)
    if not alumno.es_ppi:
        return None, False, Response({'detail': 'La documentación está disponible para alumnos PPI.'}, status=403)
    can_upload = institutional or ('Integracion' in groups and preceptor)
    return alumno, can_upload, None


def _document_data(document):
    user = document.subido_por
    return {
        'id': document.id, 'titulo': document.titulo, 'nombre_archivo': document.nombre_archivo,
        'tamano': document.tamano, 'creado_en': document.creado_en,
        'subido_por': (user.get_full_name() or user.username) if user else 'Usuario eliminado',
    }


@api_view(['GET', 'POST'])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def ppi_documents(request, alumno_id):
    alumno, can_upload, denied = _access(request, alumno_id)
    if denied is not None:
        return denied
    if request.method == 'GET':
        docs = PpiDocument.objects.filter(alumno=alumno).defer('contenido').select_related('subido_por')
        return Response({'documents': [_document_data(doc) for doc in docs], 'can_upload': can_upload})
    if not can_upload:
        return Response({'detail': 'No autorizado para subir documentos.'}, status=403)
    upload = request.FILES.get('archivo')
    title = str(request.data.get('titulo') or '').strip()
    if not title or len(title) > 200:
        return Response({'detail': 'Ingresá un título de hasta 200 caracteres.'}, status=400)
    if upload is None or not upload.name.lower().endswith('.pdf'):
        return Response({'detail': 'Seleccioná un archivo PDF.'}, status=400)
    if upload.size > MAX_PDF_BYTES:
        return Response({'detail': 'El PDF debe pesar como máximo 20 MB.'}, status=400)
    content = upload.read(MAX_PDF_BYTES + 1)
    if len(content) > MAX_PDF_BYTES or not content.startswith(b'%PDF-'):
        return Response({'detail': 'El archivo no es un PDF válido o supera 20 MB.'}, status=400)
    with transaction.atomic():
        current = Alumno.objects.select_for_update().get(pk=alumno.id)
        if not current.es_ppi:
            return Response({'detail': 'El alumno ya no está marcado como PPI.'}, status=409)
        doc = PpiDocument.objects.create(alumno=current, titulo=title, nombre_archivo=os.path.basename(upload.name)[:255], contenido=content, tamano=len(content), subido_por=request.user)
    return Response({'document': _document_data(doc)}, status=201)


@api_view(['GET'])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated])
def ppi_document_download(request, alumno_id, document_id):
    alumno, _, denied = _access(request, alumno_id)
    if denied is not None:
        return denied
    doc = PpiDocument.objects.filter(pk=document_id, alumno=alumno).first()
    if doc is None:
        return Response({'detail': 'Documento no encontrado.'}, status=404)
    response = FileResponse(io.BytesIO(bytes(doc.contenido)), content_type='application/pdf', as_attachment=True, filename=doc.nombre_archivo)
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
