# calificaciones/views/_perfil.py
# Vistas HTML index y perfil API

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from rest_framework.decorators import (
    api_view, authentication_classes, permission_classes,
)
from rest_framework.permissions import IsAuthenticated

from ..contexto import resolve_alumno_for_user
from ..jwt_auth import CookieJWTAuthentication as JWTAuthentication
from ..models import Alumno, Nota
from ..schools import (
    get_available_school_dicts_for_user,
    get_request_school,
    school_to_dict,
    scope_queryset_to_school,
)
from ..user_groups import get_user_group_names
from ._acceso import (
    _alumno_to_dict,
    _coerce_json,
    _effective_groups,
    _get_preview_role,
    _has_role,
    _mensajes_count_stats_from_qs,
    _mensajes_inbox_qs,
    _mensajes_sent_qs,
    _preceptor_assignment_refs,
    _profile_assigned_school_courses,
    _rol_principal,
)


# =========================================================
#  Vistas HTML / Index
# =========================================================
@login_required
def index(request):
    # Usa roles efectivos (respetan vista previa)
    active_school = get_request_school(request)
    is_padre = _has_role(request, 'Padres')
    is_staff_role = _has_role(request, 'Profesores', 'Directivos', 'Preceptores') or request.user.is_superuser
    puede_pasar_asistencia = bool(
        request.user.is_superuser
        or (
            _has_role(request, 'Preceptores')
            and _preceptor_assignment_refs(request.user, school=active_school)
        )
    )

    if not (is_padre or is_staff_role):
        return HttpResponse("No tienes permiso.", status=403)

    return render(
        request,
        'calificaciones/index.html',
        {
            "is_padre": is_padre,
            "is_staff_role": is_staff_role,
            "puede_pasar_asistencia": puede_pasar_asistencia,
        },
    )


# =========================================================
#  PERFIL API (GET+PATCH) para Next.js — JWT o sesión
# =========================================================
@csrf_exempt
@api_view(["GET", "PATCH"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def perfil_api(request):
    """
    - GET: datos del usuario + contexto (alumno propio, hijos, preceptor, contadores)
    - PATCH: actualiza first_name, last_name, email del usuario autenticado.
    """
    user = request.user
    active_school = get_request_school(request)

    # ===== Vista previa de rol ("Vista como…") para superusuario =====
    try:
        preview_role = _get_preview_role(request)
    except Exception:
        preview_role = None

    # Grupos efectivos
    grupos_reales = list(get_user_group_names(user))
    grupos = [preview_role] if preview_role else grupos_reales

    # Rol real + rol efectivo para UI
    try:
        rol_real = _rol_principal(user)
    except Exception:
        rol_real = grupos_reales[0] if grupos_reales else "—"
    rol = preview_role if preview_role else rol_real

    # ===== Contextos =====
    alumno_propio = None
    children = []
    assigned_school_courses = _profile_assigned_school_courses(
        user=user,
        groups=grupos,
        school=active_school,
        preview_role=preview_role,
    )
    alumno_select_qs = scope_queryset_to_school(
        Alumno.objects.select_related("school_course"),
        active_school,
    )

    # Alumno (resolucion tolerante)
    if "Alumnos" in grupos:
        r = resolve_alumno_for_user(user, school=active_school)
        if r.alumno:
            alumno_propio = _alumno_to_dict(r.alumno)
        else:
            # Fallback para vista previa: tomar cualquier alumno
            if preview_role:
                a0 = alumno_select_qs.order_by('id').first()
                alumno_propio = _alumno_to_dict(a0) if a0 else None

    # Padre
    if "Padres" in grupos:
        try:
            hijos = alumno_select_qs.filter(padre=user).order_by('curso', 'nombre')
            children = [_alumno_to_dict(x) for x in hijos]
        except Exception:
            children = []
        # Fallback vista previa: elegir un padre real y listar sus hijos
        if preview_role and not children:
            a0 = alumno_select_qs.filter(padre__isnull=False).order_by('padre_id').first()
            if a0 and a0.padre_id:
                hijos = alumno_select_qs.filter(padre_id=a0.padre_id).order_by('curso', 'nombre')
                children = [_alumno_to_dict(x) for x in hijos]

    # ===== PATCH =====
    if request.method == "PATCH":
        payload = _coerce_json(request)
        first_name = (payload.get("first_name") or "").strip()
        last_name = (payload.get("last_name") or "").strip()
        email = (payload.get("email") or "").strip()

        changed = False
        if first_name or first_name == "":
            user.first_name = first_name
            changed = True
        if last_name or last_name == "":
            user.last_name = last_name
            changed = True
        if email:
            # Evitar emails duplicados
            try:
                User = get_user_model()
                if User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
                    return JsonResponse({"detail": "Ese correo ya está en uso."}, status=400)
            except Exception:
                pass
            user.email = email
            changed = True

        if changed:
            try:
                user.full_clean(exclude=['password'])
            except Exception:
                return JsonResponse({"detail": "Datos inválidos"}, status=400)
            user.save()

    # ===== Stats =====
    if "Alumnos" in grupos and alumno_propio:
        notas_count = scope_queryset_to_school(Nota.objects.filter(alumno_id=alumno_propio["id"]), active_school).count()
    elif "Padres" in grupos and children:
        notas_count = scope_queryset_to_school(
            Nota.objects.filter(alumno_id__in=[a["id"] for a in children]),
            active_school,
        ).count()
    else:
        notas_count = 0

    # Mensajes: unificar variantes de emisor/receptor
    inbox_qs = _mensajes_inbox_qs(user, school=active_school)
    sent_qs = _mensajes_sent_qs(user, school=active_school)

    mensajes_recibidos, mensajes_no_leidos = _mensajes_count_stats_from_qs(inbox_qs)
    mensajes_enviados = sent_qs.count()

    data = {
        "user": {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "is_superuser": user.is_superuser,
            "groups": grupos,   # efectivos
            "rol": rol,         # efectivo
        },
        "alumno": alumno_propio,
        "children": children,
        "assigned_school_courses": assigned_school_courses,
        "school": school_to_dict(active_school),
        "available_schools": get_available_school_dicts_for_user(user, active_school=active_school),
        "stats": {
            "notas_count": notas_count,
            "mensajes_recibidos": mensajes_recibidos,
            "mensajes_no_leidos": mensajes_no_leidos,
            "mensajes_enviados": mensajes_enviados,
        },
    }
    return JsonResponse(data)
