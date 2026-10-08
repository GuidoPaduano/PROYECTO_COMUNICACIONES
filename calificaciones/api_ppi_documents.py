import hashlib
import io
import json
import os
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse
from django.utils import timezone
from rest_framework.decorators import api_view, authentication_classes, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .jwt_auth import CookieJWTAuthentication
from .models import Alumno, PpiDocument, PpiDocumentReceipt, Notificacion
from .models_preceptores import SchoolAdmin, ProfesorCurso, ProfesorCursoMateria
from .schools import get_request_school, get_requested_school_identifier, get_school_by_identifier
from .user_groups import get_user_group_names
from .views._acceso import _preceptor_can_access_alumno
from .ws_notify import push_unread_update_for_notification

MAX_PDF_BYTES = 20 * 1024 * 1024
DECLARATION = 'Confirmo que leí las recomendaciones de este documento.'


def _school(request):
    school = get_request_school(request)
    requested = get_requested_school_identifier(request)
    if school is None:
        return None, Response({'detail': 'Seleccioná un colegio autorizado.'}, status=403)
    if requested:
        selected = get_school_by_identifier(requested)
        if selected is None or selected.id != school.id:
            return None, Response({'detail': 'No autorizado para el colegio solicitado.'}, status=403)
    return school, None


def _teachers(alumno):
    filters = {'school_id': alumno.school_id, 'school_course_id': alumno.school_course_id}
    ids = set(ProfesorCurso.objects.filter(**filters).values_list('profesor_id', flat=True))
    ids.update(ProfesorCursoMateria.objects.filter(**filters).values_list('profesor_id', flat=True))
    return get_user_model().objects.filter(id__in=ids, is_active=True, groups__name='Profesores').distinct().order_by('last_name', 'first_name', 'id')


def _access(request, alumno_id):
    school, denied = _school(request)
    if denied is not None:
        return None, False, denied
    alumno = Alumno.objects.filter(pk=alumno_id, school=school).select_related('school_course', 'school').first()
    if alumno is None:
        return None, False, Response({'detail': 'Alumno no encontrado.'}, status=404)
    user = request.user
    groups = set(get_user_group_names(user))
    admin = user.is_superuser or ('Administradores' in groups and SchoolAdmin.objects.filter(admin=user, school=school).exists())
    institutional = admin or 'Directivos' in groups
    preceptor = 'Preceptores' in groups and _preceptor_can_access_alumno(user, alumno)
    teacher = 'Profesores' in groups and _teachers(alumno).filter(pk=user.pk).exists()
    if not (institutional or preceptor or teacher):
        return None, False, Response({'detail': 'No autorizado para este alumno.'}, status=403)
    if not alumno.es_ppi:
        return None, False, Response({'detail': 'La documentación está disponible para alumnos PPI.'}, status=403)
    can_upload = institutional or (bool({'Integracion', 'EOE'} & groups) and preceptor)
    return alumno, can_upload, None


def _documents():
    return PpiDocument.objects.defer('contenido', 'version_siguiente__contenido').select_related('alumno', 'subido_por', 'version_siguiente').prefetch_related('receipts')


def _visible_documents(alumno, user, manage):
    docs = _documents().filter(alumno=alumno)
    if not manage:
        docs = docs.filter(Q(requiere_firma=False) | Q(receipts__docente=user)).distinct()
    return docs


def _document_data(document, user, manage=False):
    uploader = document.subido_por
    receipts = list(document.receipts.all())
    own = next((r for r in receipts if r.docente_id == user.pk), None)
    superseded = hasattr(document, 'version_siguiente')
    data = {
        'id': document.id, 'alumno_id': document.alumno_id, 'alumno_nombre': str(document.alumno),
        'titulo': document.titulo, 'nombre_archivo': document.nombre_archivo,
        'tamano': document.tamano, 'creado_en': document.creado_en,
        'subido_por': (uploader.get_full_name() or uploader.username) if uploader else 'Usuario eliminado',
        'requiere_firma': document.requiere_firma, 'version': document.version,
        'version_anterior_id': document.version_anterior_id, 'reemplazado': superseded,
        'consultado_en': own.consultado_en if own else None,
        'firmado_en': own.firmado_en if own else None,
        'puede_firmar': bool(own and not own.firmado_en and not superseded and document.subido_por_id != user.id),
        'puede_gestionar': manage,
    }
    if manage:
        data['destinatarios'] = [
            {'id': r.docente_id, 'nombre': r.nombre_docente, 'firmado_en': r.firmado_en,
             'ultimo_recordatorio_en': r.ultimo_recordatorio_en} for r in receipts
        ]
    return data


def _notify(document, teacher, reminder=False):
    notification = Notificacion.objects.create(
        school_id=document.alumno.school_id, destinatario=teacher, tipo='otro',
        titulo='Recordatorio: lectura pendiente' if reminder else 'Recomendación PPI para leer y firmar',
        descripcion=f'{document.titulo} · Versión {document.version}'[:255],
        url=f'/documentacion?ppi_document={document.id}#ppi-document-{document.id}',
        meta={'ppi_document_id': document.id, 'alumno_id': document.alumno_id, 'recordatorio': reminder},
    )
    transaction.on_commit(lambda: push_unread_update_for_notification(notification))


@api_view(['GET', 'POST'])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def ppi_documents(request, alumno_id):
    alumno, can_upload, denied = _access(request, alumno_id)
    if denied is not None:
        return denied
    if request.method == 'GET':
        return Response({
            'documents': [_document_data(doc, request.user, can_upload) for doc in _visible_documents(alumno, request.user, can_upload)],
            'can_upload': can_upload,
            'docentes': [{'id': u.id, 'nombre': u.get_full_name() or u.username} for u in _teachers(alumno).exclude(pk=request.user.pk)] if can_upload else [],
        })
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
    requires_signature = str(request.data.get('requiere_firma', 'false')).lower() == 'true'
    try:
        recipients = json.loads(request.data.get('docentes', '[]'))
        if not isinstance(recipients, list) or any(type(i) is not int for i in recipients):
            raise ValueError()
        recipient_ids = set(recipients)
        previous_id = int(request.data['version_anterior_id']) if request.data.get('version_anterior_id') else None
    except (ValueError, TypeError):
        return Response({'detail': 'La selección de docentes o versión no es válida.'}, status=400)
    teachers = list(_teachers(alumno).filter(id__in=recipient_ids).exclude(pk=request.user.pk))
    if requires_signature and (not recipient_ids or recipient_ids != {u.pk for u in teachers}):
        return Response({'detail': 'Seleccioná docentes asignados a este alumno.'}, status=400)
    with transaction.atomic():
        current = Alumno.objects.select_for_update().get(pk=alumno.id)
        if not current.es_ppi:
            return Response({'detail': 'El alumno ya no está marcado como PPI.'}, status=409)
        previous = None
        if previous_id:
            previous = PpiDocument.objects.filter(pk=previous_id, alumno=current).first()
            if previous is None:
                return Response({'detail': 'Documento anterior no encontrado.'}, status=404)
            if hasattr(previous, 'version_siguiente'):
                return Response({'detail': 'Ya existe una versión más reciente. Actualizá la lista.'}, status=409)
            if previous.requiere_firma and not requires_signature:
                return Response({'detail': 'La nueva versión debe solicitar otra constancia de lectura.'}, status=400)
        doc = PpiDocument.objects.create(
            alumno=current, titulo=title, nombre_archivo=os.path.basename(upload.name)[:255],
            contenido=content, tamano=len(content), subido_por=request.user,
            requiere_firma=requires_signature, version_anterior=previous,
            version=previous.version + 1 if previous else 1, sha256=hashlib.sha256(content).hexdigest(),
        )
        if requires_signature:
            for teacher in teachers:
                PpiDocumentReceipt.objects.create(documento=doc, docente=teacher, nombre_docente=(teacher.get_full_name() or teacher.username)[:255])
                _notify(doc, teacher)
    return Response({'document': _document_data(doc, request.user, True)}, status=201)


@api_view(['GET'])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated])
def ppi_document_download(request, alumno_id, document_id):
    alumno, manage, denied = _access(request, alumno_id)
    if denied is not None:
        return denied
    doc = _visible_documents(alumno, request.user, manage).filter(pk=document_id).first()
    if doc is None:
        return Response({'detail': 'Documento no encontrado.'}, status=404)
    PpiDocumentReceipt.objects.filter(documento=doc, docente=request.user, consultado_en__isnull=True).update(consultado_en=timezone.now())
    response = FileResponse(io.BytesIO(bytes(doc.contenido)), content_type='application/pdf', as_attachment=True, filename=doc.nombre_archivo)
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@api_view(['POST'])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated])
def ppi_document_sign(request, alumno_id, document_id):
    alumno, _, denied = _access(request, alumno_id)
    if denied is not None:
        return denied
    if not isinstance(request.data, dict) or request.data.get('confirmo_lectura') is not True:
        return Response({'detail': 'Confirmá expresamente que leíste el documento.'}, status=400)
    with transaction.atomic():
        # Same lock as version publication: a superseded PDF cannot receive new signatures.
        Alumno.objects.select_for_update().get(pk=alumno.pk)
        receipt = PpiDocumentReceipt.objects.select_for_update().filter(documento_id=document_id, documento__alumno=alumno, docente=request.user).first()
        if receipt is None or receipt.documento.subido_por_id == request.user.id:
            return Response({'detail': 'No tenés una firma pendiente para este documento.'}, status=403)
        if not receipt.firmado_en:
            if hasattr(receipt.documento, 'version_siguiente'):
                return Response({'detail': 'Hay una nueva versión de este documento. Firmá la versión vigente.'}, status=409)
            if not receipt.consultado_en:
                return Response({'detail': 'Consultá el PDF antes de confirmar su lectura.'}, status=400)
            receipt.firmado_en = timezone.now()
            receipt.declaracion = DECLARATION
            receipt.save(update_fields=['firmado_en', 'declaracion'])
    return Response({'detail': 'Lectura confirmada.', 'firmado_en': receipt.firmado_en})


@api_view(['POST'])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated])
def ppi_document_remind(request, alumno_id, document_id, teacher_id):
    alumno, manage, denied = _access(request, alumno_id)
    if denied is not None:
        return denied
    if not manage:
        return Response({'detail': 'No autorizado para enviar recordatorios.'}, status=403)
    with transaction.atomic():
        Alumno.objects.select_for_update().get(pk=alumno.pk)
        receipt = PpiDocumentReceipt.objects.select_for_update().filter(documento_id=document_id, documento__alumno=alumno, docente_id=teacher_id).first()
        if receipt is None:
            return Response({'detail': 'Destinatario no encontrado.'}, status=404)
        if receipt.firmado_en or hasattr(receipt.documento, 'version_siguiente'):
            return Response({'detail': 'El documento ya está firmado o tiene una versión más reciente.'}, status=409)
        if not _teachers(alumno).filter(pk=teacher_id).exists():
            return Response({'detail': 'El docente ya no está asignado a este alumno.'}, status=400)
        now = timezone.now()
        if receipt.ultimo_recordatorio_en and now < receipt.ultimo_recordatorio_en + timedelta(hours=24):
            return Response({'detail': 'Podés enviar otro recordatorio después de 24 horas.'}, status=429)
        _notify(receipt.documento, receipt.docente, reminder=True)
        receipt.ultimo_recordatorio_en = now
        receipt.save(update_fields=['ultimo_recordatorio_en'])
    return Response({'detail': 'Recordatorio enviado.', 'ultimo_recordatorio_en': now}, status=201)


@api_view(['GET'])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated])
def ppi_document_inbox(request):
    school, denied = _school(request)
    if denied is not None:
        return denied
    docs = _documents().filter(alumno__school=school, alumno__es_ppi=True, receipts__docente=request.user).distinct()
    # Re-check current access: recipient history alone never grants access to a former course.
    visible = []
    for doc in docs:
        _, _, denied = _access(request, doc.alumno_id)
        if denied is None:
            visible.append(_document_data(doc, request.user))
    return Response({'documents': visible})
