# calificaciones/api_nueva_nota/_views.py
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import ValidationError

from rest_framework import status, permissions
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response

from ..course_access import (
    build_course_membership_q_for_refs,
    course_ref_matches,
)
from ..models import Alumno, Nota, Notificacion
from ..serializers import AlumnoSerializer, NotaCreateSerializer
from ..contexto import build_context_for_user, alumno_to_dict
from ..schools import (
    get_available_school_dicts_for_user,
    get_request_school,
    get_requested_school_identifier,
    get_school_by_identifier,
    school_to_dict,
    scope_queryset_to_school,
    user_can_access_school,
)
from ..tasks import evaluar_alerta_nota_task, evaluar_alertas_notas_bulk_task
from ..user_groups import get_user_group_names
from ._helpers import (
    _alumno_nombre,
    _build_choice_alias_map,
    _calificaciones_texto_catalogo,
    _cuatris_por_defecto,
    _cursos_catalogo,
    _cursos_profesor_asignados_refs,
    _filter_alumnos_por_curso,
    _filtrar_cursos_para_profesor,
    _is_directivo_user,
    _is_profesor_user,
    _normalize_catalog_text,
    _normalizar_nota_payload,
    _notification_course_meta,
    _notification_course_name,
    _notify_padre_nota,
    _parse_decimal_optional,
    _profesor_puede_editar_nota,
    _resultados_catalogo,
    _tipos_por_defecto,
    _usuario_puede_operar_nota_en_alumno,
    get_materias_catalogo,
)

logger = logging.getLogger(__name__)


# ---------- WhoAmI ----------
class WhoAmI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        u = request.user
        groups = list(get_user_group_names(u))
        requested_school_identifier = get_requested_school_identifier(request)
        if requested_school_identifier and not getattr(u, "is_superuser", False):
            requested_school = get_school_by_identifier(requested_school_identifier)
            if requested_school is None:
                return Response({"detail": "Colegio no encontrado."}, status=status.HTTP_404_NOT_FOUND)
            if not user_can_access_school(u, requested_school):
                return Response(
                    {"detail": "El usuario no pertenece al colegio seleccionado."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        active_school = get_request_school(request)

        # Vista previa de rol para superusuario (respeta X-Preview-Role / ?view_as=)
        try:
            from ..views import _get_preview_role
            preview_role = _get_preview_role(request)
        except Exception:
            preview_role = None
        if preview_role and getattr(u, "is_superuser", False):
            groups = [preview_role]

        full_name = (u.get_full_name() or f"{u.first_name} {u.last_name}").strip()

        # Contexto de usuario (resolucion tolerante) para que el front pueda
        # resolver "quién es el alumno" sin depender de vínculos frágiles.
        try:
            ctx = build_context_for_user(u, groups, school=active_school)
        except Exception:
            logger.exception(
                "WhoAmI: error construyendo contexto para user_id=%s",
                getattr(u, "id", None),
            )
            ctx = {}

        # Vista previa (superusuario): si simula un rol y no hay contexto real, proveo un fallback razonable.
        if preview_role and getattr(u, "is_superuser", False) and active_school is not None:
            try:
                if "Alumnos" in groups and not ctx.get("alumno"):
                    a0 = scope_queryset_to_school(Alumno.objects.all(), active_school).order_by("id").first()
                    ctx["alumno"] = alumno_to_dict(a0)
            except Exception:
                pass

        # `alumno` va arriba porque el front actual lo consume asi.
        rol = groups[0] if groups else "—"

        return Response(
            {
                "id": u.id,
                "username": u.username,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "full_name": full_name,
                "email": u.email,
                "groups": groups,
                "rol": rol,
                "is_superuser": u.is_superuser,
                "school": school_to_dict(active_school),
                "available_schools": get_available_school_dicts_for_user(u, active_school=active_school),
                **ctx,
            },
            status=status.HTTP_200_OK,
        )


# ---------- Datos iniciales para "Nueva Nota" ----------
class NuevaNotaDatosIniciales(APIView):
    """
    GET /api/calificaciones/nueva-nota/datos/?school_course_id=14
    Usa school_course_id para filtrar por curso.
    Devuelve alumnos (opcionalmente filtrados por curso),
    catálogo de materias, tipos y cuatrimestres.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        from ..utils_cursos import resolve_course_reference
        active_school = get_request_school(request)
        school_course, curso, course_error = resolve_course_reference(
            school=active_school,
            raw_course=request.query_params.get("curso"),
            raw_school_course_id=request.query_params.get("school_course_id"),
            required=False,
        )
        if course_error:
            return Response({"detail": course_error}, status=status.HTTP_400_BAD_REQUEST)
        assigned_course_refs = []
        try:
            if _is_profesor_user(request.user):
                assigned_course_refs = _cursos_profesor_asignados_refs(request.user, school=active_school)
        except Exception:
            assigned_course_refs = []

        if (school_course is not None or curso) and assigned_course_refs and not course_ref_matches(
            assigned_course_refs,
            school_course_id=getattr(school_course, "id", None),
            course_code=curso,
        ):
            return Response({"detail": "No tenés permiso para ese curso."}, status=status.HTTP_403_FORBIDDEN)

        cursos_catalogo = _filtrar_cursos_para_profesor(
            request.user,
            _cursos_catalogo(school=active_school),
            school=active_school,
        )
        selected_course = None
        if school_course is not None:
            selected_course = next(
                (c for c in cursos_catalogo if c.get("school_course_id") == getattr(school_course, "id", None)),
                None,
            )
        if selected_course is None and curso:
            selected_course = next(
                (c for c in cursos_catalogo if str(c.get("code") or c.get("id") or "").strip() == curso),
                None,
            )
        if selected_course is None and cursos_catalogo:
            selected_course = cursos_catalogo[0]

        school_course_id_inicial = None
        school_course_name_inicial = ""
        selected_course_code = ""
        if selected_course is not None:
            selected_course_code = str(selected_course.get("code") or selected_course.get("id") or "").strip()
            school_course_id_inicial = selected_course.get("school_course_id")
            school_course_name_inicial = str(selected_course.get("nombre") or "").strip()

        alumnos_qs = scope_queryset_to_school(
            Alumno.objects.only(
                "id", "id_alumno", "nombre", "apellido", "curso",
                "school_course_id",
                "school_course__id", "school_course__code", "school_course__name",
            ).select_related("school_course"),
            active_school,
        ).order_by("nombre")
        if selected_course_code:
            alumnos_qs = _filter_alumnos_por_curso(alumnos_qs, selected_course_code, school=active_school)
        elif assigned_course_refs:
            allowed_course_q = build_course_membership_q_for_refs(
                assigned_course_refs,
                school_course_field="school_course",
                code_field="curso",
            )
            alumnos_qs = alumnos_qs.filter(allowed_course_q) if allowed_course_q is not None else alumnos_qs.none()

        data = {
            "alumnos": AlumnoSerializer(alumnos_qs, many=True).data,
            "cursos": cursos_catalogo,
            "school_course_id_inicial": school_course_id_inicial,
            "school_course_name_inicial": school_course_name_inicial,
            "materias": get_materias_catalogo(),
            "tipos": _tipos_por_defecto(),
            "cuatrimestres": _cuatris_por_defecto(),
            "resultados": _resultados_catalogo(),
            "calificaciones": _calificaciones_texto_catalogo(),
            "hoy": timezone.localdate(),
        }
        return Response(data, status=status.HTTP_200_OK)


class CrearNota(APIView):
    """
    POST /api/calificaciones/notas/
    Body JSON:
    {
      alumno | alumno_id | id_alumno,
      materia,
      tipo,
      resultado?,         # TEA/TEP/TED
      nota_numerica?,     # 1..10
      calificacion?,      # campo heredado
      cuatrimestre,
      fecha?
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        active_school = get_request_school(request)
        payload = _normalizar_nota_payload(request.data, school=active_school)
        serializer = NotaCreateSerializer(data=payload)
        if serializer.is_valid():
            alumno = serializer.validated_data.get("alumno")
            if alumno is None or not _usuario_puede_operar_nota_en_alumno(request.user, alumno):
                return Response(
                    {"detail": "No tenés permiso para cargar notas para ese alumno."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            # Upsert para notas finales: si ya existe una, actualizarla
            if serializer.validated_data.get("es_final"):
                existing = scope_queryset_to_school(
                    Nota.objects.filter(
                        alumno=alumno,
                        materia=serializer.validated_data.get("materia"),
                        cuatrimestre=serializer.validated_data.get("cuatrimestre"),
                        anio_lectivo=serializer.validated_data.get("anio_lectivo"),
                        es_final=True,
                    ),
                    active_school,
                ).first()
                if existing:
                    nota = serializer.update(existing, dict(serializer.validated_data))
                else:
                    nota = serializer.save()
            else:
                nota = serializer.save()
            school_ref = getattr(getattr(nota, "alumno", None), "school", None) or active_school
            if school_ref is not None and getattr(nota, "school_id", None) is None:
                nota.school = school_ref
                nota.save(update_fields=["school"])
            notificado, notif_dest_id, notif_source, notif_error = _notify_padre_nota(request.user, nota)
            try:
                evaluar_alerta_nota_task.delay(
                    nota_id=nota.pk,
                    actor_id=getattr(request.user, "pk", None),
                )
            except Exception:
                pass
            resp = {
                "id": nota.id,
                "version": nota.version,
                "notificado": notificado,
                "notif_destinatario_id": notif_dest_id,
                "notif_source": notif_source,
                "alerta_queued": True,
            }
            # Si sos staff/superuser y falló, devolvemos error para debug
            if (not notificado) and notif_error and (
                getattr(request.user, "is_superuser", False) or _is_directivo_user(request.user)
            ):
                resp["notif_error"] = notif_error
            return Response(resp, status=status.HTTP_201_CREATED)
        return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


class EditarNota(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, nota_id, *args, **kwargs):
        active_school = get_request_school(request)
        try:
            nota = scope_queryset_to_school(
                Nota.objects.select_related("alumno"),
                active_school,
            ).get(pk=nota_id)
        except Nota.DoesNotExist:
            return Response({"detail": "Nota no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        if not _profesor_puede_editar_nota(request.user, nota):
            return Response({"detail": "No tenés permiso para editar esta nota."}, status=status.HTTP_403_FORBIDDEN)

        try:
            expected_version = int(request.data.get("version"))
        except (TypeError, ValueError):
            return Response(
                {"detail": "La versión de la nota es obligatoria para editarla."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if expected_version < 1:
            return Response(
                {"detail": "La versión de la nota no es válida."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = _normalizar_nota_payload(request.data, school=active_school)
        payload.pop("version", None)
        payload["alumno"] = nota.alumno_id

        serializer = NotaCreateSerializer(instance=nota, data=payload, partial=True)
        if not serializer.is_valid():
            return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        updates = dict(serializer.validated_data)
        updates.pop("alumno", None)
        updated = scope_queryset_to_school(Nota.objects.all(), active_school).filter(
            pk=nota.pk,
            version=expected_version,
        ).update(**updates, version=F("version") + 1)
        if updated != 1:
            current = scope_queryset_to_school(Nota.objects.all(), active_school).get(pk=nota.pk)
            return Response(
                {
                    "detail": (
                        "La nota fue modificada por otra sesión. "
                        "Revisá la versión actual antes de volver a guardar."
                    ),
                    "nota": NotaCreateSerializer(current).data,
                },
                status=status.HTTP_409_CONFLICT,
            )

        nota.refresh_from_db()
        return Response({"nota": NotaCreateSerializer(nota).data}, status=status.HTTP_200_OK)


# ---------- Crear varias notas (bulk JSON) ----------
@method_decorator(csrf_exempt, name="dispatch")
class CrearNotasMasivo(APIView):
    """    POST /api/calificaciones/notas/masivo/
    Body JSON:
      {"notas": [{...}, {...}]}

    OPTIMIZADO (Railway-friendly):
    - Resuelve alumnos en 1 query (pk/id_alumno)
    - Valida sin instanciar serializers por fila (evita N queries)
    - bulk_create de Notas (1 insert batch)
    - Notificaciones: 1 por alumno+destinatario (padre/alumno) usando bulk_create

    Cada item puede usar 'alumno', 'alumno_id' (pk) o 'id_alumno' (legajo).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        active_school = get_request_school(request)
        body = request.data
        notas_in = body.get("notas") if isinstance(body, dict) else None
        if not isinstance(notas_in, list):
            return Response(
                {"error": "Formato inválido: se espera {'notas': [ ... ]}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ------------------------
        # 0) Helpers locales
        # ------------------------
        allowed_materias_map = _build_choice_alias_map(
            getattr(Nota, "MATERIAS", []),
            get_materias_catalogo(),
        )
        allowed_tipos_map = _build_choice_alias_map(
            getattr(Nota, "TIPOS", []),
            getattr(Nota, "TIPO_NOTA_CHOICES", []),
            _tipos_por_defecto(),
        )

        def _get_alumno_key(item):
            if not isinstance(item, dict):
                return None
            v = item.get('alumno', item.get('alumno_id', item.get('id_alumno')))
            if v is None:
                return None
            sv = str(v).strip()
            return sv or None

        # ------------------------
        # 1) Resolver alumnos en bloque (1 query)
        # ------------------------
        keys = []
        for it in notas_in:
            k = _get_alumno_key(it)
            if k is not None:
                keys.append(k)
        keys_unique = sorted(set(keys))

        alumnos_by_pk = {}
        alumnos_by_legajo_lower = {}

        if keys_unique:
            numeric_ids = []
            legajos = []
            for k in keys_unique:
                if k.isdigit():
                    try:
                        numeric_ids.append(int(k))
                    except Exception:
                        pass
                legajos.append(k)

            # Q por pk e id_alumno (incluye variantes de case)
            q = Q()
            if numeric_ids:
                q |= Q(pk__in=numeric_ids)
            if legajos:
                q |= Q(id_alumno__in=legajos) | Q(id_alumno__in=[x.upper() for x in legajos]) | Q(id_alumno__in=[x.lower() for x in legajos])

            qs = (
                scope_queryset_to_school(Alumno.objects.filter(q), active_school)
                .select_related("padre", "usuario")
                .only(
                    "id",
                    "id_alumno",
                    "curso",
                    "school",
                    "padre_id",
                    "usuario_id",
                    "nombre",
                    "apellido",
                    "padre__id",
                    "usuario__id",
                )
            )
            for a in qs:
                alumnos_by_pk[a.pk] = a
                try:
                    leg = (getattr(a, 'id_alumno', '') or '').strip()
                    if leg:
                        alumnos_by_legajo_lower[leg.lower()] = a
                except Exception:
                    pass

        def _resolve_alumno(k: str):
            if not k:
                return None
            # si viene numérico, primero intento PK; si no existe, caigo a legajo
            if k.isdigit():
                try:
                    a = alumnos_by_pk.get(int(k))
                    if a is not None:
                        return a
                except Exception:
                    pass
            return alumnos_by_legajo_lower.get(k.lower())

        # ------------------------
        # 2) Validación rápida + construcción de Nota objs
        # ------------------------
        errors = []
        notas_objs = []
        today = timezone.localdate()

        for idx, item in enumerate(notas_in):
            if not isinstance(item, dict):
                errors.append({"index": idx, "errors": {"__all__": ["Item inválido (no es objeto)"]}})
                continue

            alumno_key = _get_alumno_key(item)
            alumno = _resolve_alumno(alumno_key) if alumno_key else None
            if alumno is None:
                errors.append({"index": idx, "errors": {"alumno": ["Alumno inválido o inexistente."]}})
                continue
            if not _usuario_puede_operar_nota_en_alumno(request.user, alumno):
                errors.append(
                    {"index": idx, "errors": {"alumno": ["No tenés permiso para cargar notas para ese alumno."]}}
                )
                continue

            materia = (item.get('materia') or '').strip()
            tipo = (item.get('tipo') or '').strip()
            calif_raw = item.get('calificacion')
            calif = str(calif_raw or '').strip().upper()
            resultado = str(item.get('resultado') or '').strip().upper()
            nota_numerica_raw = item.get("nota_numerica", item.get("notaNumerica"))
            nota_numerica = _parse_decimal_optional(nota_numerica_raw)
            cuatri_raw = item.get('cuatrimestre')
            fecha_raw = item.get('fecha', None)

            row_err = {}
            materia_canon = allowed_materias_map.get(_normalize_catalog_text(materia)) if materia else None
            tipo_canon = allowed_tipos_map.get(_normalize_catalog_text(tipo)) if tipo else None

            if not materia:
                row_err.setdefault('materia', []).append('Materia requerida.')
            elif allowed_materias_map and materia_canon is None:
                row_err.setdefault('materia', []).append('Materia inválida.')
            else:
                materia = materia_canon or materia

            if not tipo:
                row_err.setdefault('tipo', []).append('Tipo requerido.')
            elif allowed_tipos_map and tipo_canon is None:
                row_err.setdefault('tipo', []).append('Tipo inválido.')
            else:
                tipo = tipo_canon or tipo

            if resultado and resultado not in {"TEA", "TEP", "TED"}:
                row_err.setdefault("resultado", []).append("Resultado inválido. Usá TEA, TEP o TED.")

            if nota_numerica_raw not in (None, "") and nota_numerica is None:
                row_err.setdefault("nota_numerica", []).append("La nota_numerica debe estar entre 1 y 10.")

            if calif:
                try:
                    from ..models import validate_calificacion_ext
                    validate_calificacion_ext(calif)
                except ValidationError as ve:
                    row_err.setdefault('calificacion', []).append(str(ve))
                except Exception:
                    row_err.setdefault('calificacion', []).append('Calificación inválida.')

            if calif and calif in {"TEA", "TEP", "TED"} and not resultado:
                resultado = calif
            if calif and nota_numerica is None:
                parsed_from_calif = _parse_decimal_optional(calif)
                if parsed_from_calif is not None:
                    nota_numerica = parsed_from_calif

            if not calif:
                if resultado:
                    calif = resultado
                elif nota_numerica is not None:
                    calif = str(nota_numerica).rstrip("0").rstrip(".")

            if (not calif) and (not resultado) and (nota_numerica is None):
                row_err.setdefault("resultado", []).append(
                    "Debés informar resultado, nota_numerica o calificacion."
                )

            try:
                cuatri = int(cuatri_raw)
                if cuatri not in (1, 2):
                    raise ValueError()
            except Exception:
                row_err.setdefault('cuatrimestre', []).append('El cuatrimestre debe ser 1 o 2.')
                cuatri = None

            fecha = None
            if fecha_raw in (None, ''):
                fecha = today
            else:
                try:
                    # soporta YYYY-MM-DD
                    fecha = parse_date(str(fecha_raw).strip())
                    if not fecha:
                        raise ValueError('fecha inválida')
                except Exception:
                    row_err.setdefault('fecha', []).append('fecha inválida (formato YYYY-MM-DD).')

            if row_err:
                errors.append({"index": idx, "errors": row_err})
                continue

            notas_objs.append(
                Nota(
                    alumno=alumno,
                    school=getattr(alumno, "school", None) or active_school,
                    materia=materia,
                    tipo=tipo,
                    calificacion=calif,
                    resultado=(resultado or None),
                    nota_numerica=nota_numerica,
                    cuatrimestre=cuatri,
                    fecha=fecha,
                )
            )

        if not notas_objs:
            return Response(
                {"created": [], "errors": errors, "notificados": 0},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ------------------------
        # 3) Guardar (bulk) + Notificaciones (bulk, sin N queries)
        # ------------------------
        created_ids = []
        notificados = 0
        alertas_creadas = 0

        # prefetch de users por legajo (1 query)
        User = get_user_model()
        legajos = []
        for n in notas_objs:
            try:
                leg = (getattr(n.alumno, 'id_alumno', '') or '').strip()
                if leg:
                    legajos.append(leg)
            except Exception:
                pass
        legajos = sorted(set(legajos))

        users_by_username_lower = {}
        if legajos:
            qs_u = User.objects.filter(
                Q(username__in=legajos) | Q(username__in=[x.upper() for x in legajos]) | Q(username__in=[x.lower() for x in legajos])
            ).only('id', 'username')
            for u in qs_u:
                try:
                    users_by_username_lower[(u.username or '').lower()] = u
                except Exception:
                    pass

        destinatarios_cache = {}

        def _destinatarios_para_alumno(a: Alumno):
            aid = getattr(a, "id", None)
            if aid is not None and aid in destinatarios_cache:
                return destinatarios_cache[aid]

            destinatarios = []
            seen = set()

            def _add(u):
                if u is None:
                    return
                uid = getattr(u, 'id', None)
                if uid is None or uid in seen:
                    return
                seen.add(uid)
                destinatarios.append(u)

            # padre
            _add(getattr(a, 'padre', None))
            # usuario directo
            _add(getattr(a, 'usuario', None))
            # username==legajo
            try:
                leg = (getattr(a, 'id_alumno', '') or '').strip().lower()
                if leg:
                    _add(users_by_username_lower.get(leg))
            except Exception:
                pass

            if aid is not None:
                destinatarios_cache[aid] = destinatarios
            return destinatarios

        docente = (request.user.get_full_name() or request.user.username).strip()

        alert_candidates = {}

        with transaction.atomic():
            Nota.objects.bulk_create(notas_objs, batch_size=500)
            created_ids = [getattr(n, 'id', None) for n in notas_objs if getattr(n, 'id', None) is not None]

            # Agrupar para 1 notificación por (destinatario, alumno)
            grupos = {}
            for n in notas_objs:
                a = n.alumno
                dests = _destinatarios_para_alumno(a)
                if not dests:
                    continue
                for d in dests:
                    key = (getattr(d, 'id', None), getattr(a, 'id', None))
                    if key not in grupos:
                        grupos[key] = {"dest": d, "alumno": a, "curso": getattr(a, 'curso', '') or '', "notas": []}
                    grupos[key]["notas"].append(n)

            notifs = []
            for g in grupos.values():
                a = g['alumno']
                alumno_full = _alumno_nombre(a)
                curso = g['curso']
                course_name = _notification_course_name(alumno=a, course_code=curso)
                notas_alumno = g['notas']

                titulo = (f"Nuevas notas para {alumno_full}" if len(notas_alumno) > 1 else f"Nueva nota para {alumno_full}")

                # lines compactas
                lines = []
                for nn in notas_alumno:
                    f = getattr(nn, 'fecha', None)
                    fstr = f.isoformat() if hasattr(f, 'isoformat') else ''
                    base = f"• {getattr(nn, 'materia', '')} ({getattr(nn, 'tipo', '')}): {getattr(nn, 'calificacion', '')}".strip()
                    if fstr:
                        base += f" — {fstr}"
                    lines.append(base)

                descripcion = (
                    "Se registraron nuevas calificaciones. "
                    f"Alumno: {alumno_full}. "
                    + (f"Curso: {course_name}. " if course_name else "")
                    + (" ".join(lines) if lines else "")
                    + (f" Docente: {docente}" if docente else "")
                ).strip()

                notifs.append(
                    Notificacion(
                        school=getattr(a, "school", None) or active_school,
                        destinatario=g['dest'],
                        tipo='nota',
                        titulo=titulo,
                        descripcion=descripcion,
                        url=f"/alumnos/{getattr(a, 'id', '')}/?tab=notas",
                        leida=False,
                        meta={
                            "alumno_id": getattr(a, 'id', None),
                            "nota_ids": [getattr(x, 'id', None) for x in notas_alumno],
                            **_notification_course_meta(alumno=a, course_code=curso, school=active_school),
                            "docente": docente,
                        },
                    )
                )

            if notifs:
                Notificacion.objects.bulk_create(notifs, batch_size=500)
                notificados = len(notifs)

            for n in notas_objs:
                key = (
                    getattr(n, "alumno_id", None),
                    getattr(n, "materia", ""),
                    getattr(n, "cuatrimestre", None),
                )
                prev = alert_candidates.get(key)
                if prev is None:
                    alert_candidates[key] = n
                    continue

                prev_fecha = getattr(prev, "fecha", None)
                curr_fecha = getattr(n, "fecha", None)
                prev_id = getattr(prev, "id", 0) or 0
                curr_id = getattr(n, "id", 0) or 0
                if (curr_fecha, curr_id) >= (prev_fecha, prev_id):
                    alert_candidates[key] = n

        try:
            evaluar_alertas_notas_bulk_task.delay(
                nota_ids=[n.pk for n in alert_candidates.values()],
                actor_id=getattr(request.user, "pk", None),
            )
        except Exception:
            logger.exception("Error encolando alertas academicas en carga masiva")

        # 207 si hubo errores parciales, 201 si todo ok
        if errors:
            return Response(
                {"created": created_ids, "errors": errors, "notificados": notificados, "alertas": alertas_creadas},
                status=207,
            )

        return Response({"created": created_ids, "notificados": notificados, "alertas": alertas_creadas}, status=status.HTTP_201_CREATED)
