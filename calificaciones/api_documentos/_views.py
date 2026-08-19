from django.db.models import Q
from django.http import FileResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..jwt_auth import CookieJWTAuthentication as JWTAuthentication
from ..models import Alumno, Documento, FirmaDocumento, SchoolCourse
from ..schools import get_request_school

try:
    from ..models_preceptores import PreceptorCurso
except ImportError:
    PreceptorCurso = None


def _has_role(request, *roles):
    groups = set(request.user.groups.values_list("name", flat=True))
    return any(r in groups for r in roles)


def _can_upload(request):
    return (
        getattr(request.user, "is_superuser", False)
        or _has_role(request, "Directivos", "Preceptores")
    )


def _get_client_ip(request):
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _preceptor_course_ids(user, school):
    """IDs de school_course asignados al preceptor en esta escuela."""
    if PreceptorCurso is None:
        return None
    qs = PreceptorCurso.objects.filter(preceptor=user, school=school).values_list("school_course_id", flat=True)
    ids = set(qs)
    return ids if ids else set()


def _curso_ids_for_user(user, school):
    """
    Devuelve los school_course_id visibles para el usuario:
    - Superuser / Directivos: todos (None)
    - Preceptores: solo sus cursos asignados
    - Padres: cursos de sus hijos
    - Alumnos: su propio curso
    Retorna None si el usuario ve todos los cursos.
    """
    if getattr(user, "is_superuser", False):
        return None
    groups = set(user.groups.values_list("name", flat=True))

    if groups & {"Directivos"}:
        return None

    if "Preceptores" in groups:
        return _preceptor_course_ids(user, school)

    ids = set()
    if "Padres" in groups:
        for a in Alumno.objects.filter(padre=user, school=school).select_related("school_course"):
            if a.school_course_id:
                ids.add(a.school_course_id)
    elif "Alumnos" in groups:
        try:
            a = Alumno.objects.filter(usuario=user, school=school).select_related("school_course").first()
            if a and a.school_course_id:
                ids.add(a.school_course_id)
        except Exception:
            pass
    return ids


def _documento_to_dict(doc, user=None):
    firmado = False
    if user and user.is_authenticated:
        firmado = FirmaDocumento.objects.filter(documento=doc, usuario=user).exists()

    course = doc.school_course
    return {
        "id": doc.id,
        "titulo": doc.titulo,
        "descripcion": doc.descripcion,
        "tipo": doc.tipo,
        "tipo_display": doc.get_tipo_display(),
        "archivo_url": doc.archivo.url if doc.archivo else None,
        "requiere_firma": doc.requiere_firma,
        "creado_en": doc.creado_en.isoformat(),
        "subido_por": (
            doc.subido_por.get_full_name() or doc.subido_por.username
            if doc.subido_por else None
        ),
        "firmado": firmado,
        "total_firmas": doc.firmas.count(),
        "school_course_id": course.id if course else None,
        "school_course_name": (getattr(course, "name", None) or getattr(course, "code", None)) if course else None,
    }


@csrf_exempt
@api_view(["GET", "POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def documentos_list(request):
    """
    GET  /api/documentos/  → lista documentos visibles para el usuario
    POST /api/documentos/  → sube un nuevo documento (admin/preceptor)
    """
    school = get_request_school(request)
    if not school:
        return Response({"detail": "No se pudo determinar la escuela."}, status=400)

    if request.method == "GET":
        curso_ids = _curso_ids_for_user(request.user, school)
        qs = Documento.objects.filter(school=school).select_related("school_course", "subido_por")
        if curso_ids is not None:
            # Ve documentos sin curso asignado (toda la institución) + los de sus cursos
            qs = qs.filter(Q(school_course__isnull=True) | Q(school_course_id__in=curso_ids))
        return Response({"documentos": [_documento_to_dict(d, request.user) for d in qs]})

    # POST — solo admin/preceptores
    if not _can_upload(request):
        return Response({"detail": "No tenés permiso para subir documentos."}, status=403)

    titulo = (request.data.get("titulo") or "").strip()
    if not titulo:
        return Response({"detail": "El título es requerido."}, status=400)

    archivo = request.FILES.get("archivo")
    if not archivo:
        return Response({"detail": "El archivo PDF es requerido."}, status=400)

    if not archivo.name.lower().endswith(".pdf"):
        return Response({"detail": "Solo se permiten archivos PDF."}, status=400)

    school_course = None
    school_course_id = request.data.get("school_course_id")
    if school_course_id:
        try:
            school_course = SchoolCourse.objects.get(id=int(school_course_id), school=school)
        except (SchoolCourse.DoesNotExist, ValueError):
            return Response({"detail": "Curso no encontrado."}, status=400)

    doc = Documento.objects.create(
        school=school,
        school_course=school_course,
        titulo=titulo,
        descripcion=(request.data.get("descripcion") or "").strip(),
        tipo=request.data.get("tipo") or "otro",
        archivo=archivo,
        subido_por=request.user,
        requiere_firma=str(request.data.get("requiere_firma", "true")).lower() != "false",
    )
    return Response(_documento_to_dict(doc, request.user), status=201)


@csrf_exempt
@api_view(["GET", "DELETE"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def documento_detail(request, doc_id):
    school = get_request_school(request)
    try:
        doc = Documento.objects.get(id=doc_id, school=school)
    except Documento.DoesNotExist:
        return Response({"detail": "Documento no encontrado."}, status=404)

    if request.method == "GET":
        return Response(_documento_to_dict(doc, request.user))

    if not _can_upload(request):
        return Response({"detail": "No tenés permiso para eliminar documentos."}, status=403)

    try:
        doc.archivo.delete(save=False)
    except Exception:
        pass  # Si falla borrar el archivo en R2, igual eliminamos el registro

    try:
        doc.delete()
    except Exception as e:
        return Response({"detail": f"Error al eliminar el registro: {e}"}, status=500)

    return Response({"detail": "Documento eliminado."})


@csrf_exempt
@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def documento_firmar(request, doc_id):
    school = get_request_school(request)
    try:
        doc = Documento.objects.get(id=doc_id, school=school)
    except Documento.DoesNotExist:
        return Response({"detail": "Documento no encontrado."}, status=404)

    if not doc.requiere_firma:
        return Response({"detail": "Este documento no requiere firma."}, status=400)

    _, created = FirmaDocumento.objects.get_or_create(
        documento=doc,
        usuario=request.user,
        defaults={"ip_address": _get_client_ip(request)},
    )

    if not created:
        return Response({"detail": "Ya habías firmado este documento.", "firmado": True})

    return Response({"detail": "Documento firmado correctamente.", "firmado": True}, status=201)


@csrf_exempt
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def documento_firmas(request, doc_id):
    if not _can_upload(request):
        return Response({"detail": "No tenés permiso para ver las firmas."}, status=403)

    school = get_request_school(request)
    try:
        doc = Documento.objects.get(id=doc_id, school=school)
    except Documento.DoesNotExist:
        return Response({"detail": "Documento no encontrado."}, status=404)

    firmas = doc.firmas.select_related("usuario").all()
    return Response({
        "documento": doc.titulo,
        "total_firmas": firmas.count(),
        "firmas": [
            {
                "usuario_id": f.usuario_id,
                "nombre": f.usuario.get_full_name() or f.usuario.username,
                "email": f.usuario.email,
                "fecha_firma": f.fecha_firma.isoformat(),
            }
            for f in firmas
        ],
    })


@csrf_exempt
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def documento_archivo(request, doc_id):
    """
    GET /api/documentos/<id>/archivo/
    Sirve el PDF como proxy para evitar problemas de autenticación con R2/S3.
    """
    school = get_request_school(request)
    try:
        doc = Documento.objects.get(id=doc_id, school=school)
    except Documento.DoesNotExist:
        return Response({"detail": "Documento no encontrado."}, status=404)

    if not doc.archivo:
        return Response({"detail": "El documento no tiene archivo."}, status=404)

    try:
        f = doc.archivo.open("rb")
        import os
        filename = os.path.basename(doc.archivo.name)
        response = FileResponse(f, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        response["X-Frame-Options"] = "SAMEORIGIN"
        return response
    except Exception as e:
        return HttpResponse(f"Error al leer el archivo: {e}", status=500, content_type="text/plain")
