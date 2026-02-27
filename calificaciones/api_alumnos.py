# calificaciones/api_alumnos.py
import re

from django.db import IntegrityError, transaction
from django.views.decorators.csrf import csrf_exempt

from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    parser_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.parsers import JSONParser
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import Alumno
from .utils_cursos import filtrar_cursos_validos, is_curso_valido

try:
    from .models_preceptores import PreceptorCurso  # type: ignore
except Exception:
    PreceptorCurso = None


def _is_valid_curso(curso: str) -> bool:
    return is_curso_valido(curso)


def _alumno_to_dict(a: Alumno) -> dict:
    # Mantengo el formato que ya venías usando en crear_alumno
    return {
        "id": a.id,
        "id_alumno": a.id_alumno,
        "nombre": getattr(a, "nombre", None),
        "apellido": getattr(a, "apellido", None),
        "curso": getattr(a, "curso", None),
        "padre": getattr(a, "padre_id", None),
        # Si existe el campo usuario (OneToOne/FK), lo exponemos como id (si no existe, queda None)
        "usuario": getattr(a, "usuario_id", None) if hasattr(a, "usuario_id") else None,
    }


def _normalizar_prefijo_curso(curso: str) -> str:
    # Solo letras/números para que el legajo quede “limpio” (ej: 1A, 4NAT)
    return re.sub(r"[^A-Za-z0-9]", "", str(curso or "")).upper()


def _generar_id_alumno_para_curso(curso: str) -> str:
    """
    Genera un id_alumno único si el frontend lo deja vacío (campo "opcional").

    Formato: <CURSO><NNN>
      - 1A001, 1A002...
      - 4NAT001...

    Nota: no depende de DB-specific functions; trae los existentes y resuelve en Python.
    """
    pref = _normalizar_prefijo_curso(curso)
    if not pref:
        pref = "AL"

    existentes = list(
        Alumno.objects.filter(id_alumno__istartswith=pref)
        .values_list("id_alumno", flat=True)
    )

    upper = {str(x).upper() for x in existentes if x}

    max_n = 0
    rgx = re.compile(rf"^{re.escape(pref)}(\\d+)$", re.IGNORECASE)
    for s in upper:
        m = rgx.match(s)
        if m:
            try:
                max_n = max(max_n, int(m.group(1)))
            except Exception:
                pass

    n = max_n + 1
    # Seguridad: por si hay huecos o id raros; igual debería cortar rápido.
    for _ in range(1, 5000):
        cand = f"{pref}{n:03d}"
        if cand.upper() not in upper:
            return cand
        n += 1

    # Último recurso (muy improbable)
    return f"{pref}{max_n + 1:03d}"


def _is_preceptor_user(user) -> bool:
    try:
        if user is None:
            return False
        return user.groups.filter(name__in=["Preceptores", "Preceptor"]).exists()
    except Exception:
        return False


def _resolve_alumno_for_transfer(data) -> Alumno | None:
    alumno_id = data.get("alumno_id") or data.get("id")
    legajo = data.get("id_alumno") or data.get("legajo")

    if alumno_id:
        try:
            return Alumno.objects.get(pk=int(alumno_id))
        except Exception:
            return None

    if legajo:
        try:
            return Alumno.objects.get(id_alumno__iexact=str(legajo).strip())
        except Exception:
            return None

    return None


@csrf_exempt
@api_view(["POST"])
@parser_classes([JSONParser])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def crear_alumno(request):
    """
    POST /alumnos/crear/
    JSON:
      {
        "id_alumno": "A00123",   # opcional (si no viene, se genera)
        "nombre": "Luca",        # requerido (si no viene, se usa el id_alumno)
        "apellido": "Cabrera",   # opcional ("" por defecto)
        "curso": "1A"            # requerido (debe pertenecer a Alumno.CURSOS)
      }
    """
    data = request.data or {}
    # Soportamos "legajo" como alias
    id_alumno = (data.get("id_alumno") or data.get("legajo") or "").strip()
    nombre = (data.get("nombre") or "").strip()
    apellido = (data.get("apellido") or "").strip()
    curso = (data.get("curso") or "").strip()

    if not curso:
        return Response({"detail": "Falta el campo requerido: curso."}, status=400)
    if not _is_valid_curso(curso):
        return Response({"detail": f"Curso inválido: {curso}."}, status=400)

    # ✅ id_alumno ahora es realmente opcional (si no viene, lo generamos)
    if not id_alumno:
        id_alumno = _generar_id_alumno_para_curso(curso)

    # El modelo requiere nombre; si el frontend manda solo legajo, ponemos algo razonable.
    if not nombre:
        nombre = id_alumno

    # Crear de forma segura (por si justo colisiona el legajo generado)
    try:
        with transaction.atomic():
            a = Alumno.objects.create(
                id_alumno=id_alumno,
                nombre=nombre,
                apellido=apellido,
                curso=curso,
                padre=None,  # opcional; se puede asociar luego
            )
    except IntegrityError:
        # Si el usuario lo escribió y chocó, devolvemos el error claro.
        # Si lo generamos y chocó por carrera, reintentamos 1 vez.
        if (data.get("id_alumno") or data.get("legajo")):
            return Response({"detail": "El id_alumno (legajo) ya existe."}, status=400)

        try:
            id_alumno2 = _generar_id_alumno_para_curso(curso)
            with transaction.atomic():
                a = Alumno.objects.create(
                    id_alumno=id_alumno2,
                    nombre=nombre,
                    apellido=apellido,
                    curso=curso,
                    padre=None,
                )
        except IntegrityError:
            return Response({"detail": "No se pudo generar un id_alumno único."}, status=400)

    return Response(
        {
            "ok": True,
            "alumno": _alumno_to_dict(a),
        },
        status=201,
    )


@csrf_exempt
@api_view(["POST"])
@parser_classes([JSONParser])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def vincular_mi_legajo(request):
    """
    POST /alumnos/vincular/
    Vincula el usuario autenticado al registro Alumno (por legajo/id_alumno).
    Esto resuelve de forma explícita el problema de "no pudimos determinar tu alumno".

    JSON:
      {
        "id_alumno": "A00123"
      }

    Reglas:
    - Busca Alumno por id_alumno (case-insensitive).
    - Si el Alumno ya está vinculado a OTRO usuario -> 409.
    - Si ya está vinculado al mismo usuario -> 200 (idempotente).
    - Si está libre -> vincula y devuelve 200.
    """
    data = request.data or {}
    id_alumno = (data.get("id_alumno") or data.get("legajo") or "").strip()

    if not id_alumno:
        return Response({"detail": "Falta id_alumno (legajo)."}, status=400)

    qs = Alumno.objects.filter(id_alumno__iexact=id_alumno)
    a = qs.first()
    if not a:
        return Response({"detail": "No existe un alumno con ese id_alumno (legajo)."}, status=404)

    # Si tu modelo todavía no tiene campo `usuario`, esto fallaría al intentar vincular.
    # Preferimos devolver un error explícito y útil.
    if not hasattr(a, "usuario_id"):
        return Response(
            {
                "detail": "El modelo Alumno no tiene el campo 'usuario'. "
                          "Necesitás agregarlo (OneToOne/FK) para poder vincular alumno↔usuario."
            },
            status=500,
        )

    # Conflicto: ya vinculado a otro usuario
    if a.usuario_id and a.usuario_id != request.user.id:
        return Response(
            {
                "detail": "Este alumno ya está vinculado a otro usuario.",
                "alumno": _alumno_to_dict(a),
            },
            status=409,
        )

    # Idempotente: ya está vinculado a este usuario
    if a.usuario_id == request.user.id:
        return Response(
            {
                "ok": True,
                "already_linked": True,
                "alumno": _alumno_to_dict(a),
            },
            status=200,
        )

    # Vincular
    a.usuario = request.user
    a.save(update_fields=["usuario"])

    return Response(
        {
            "ok": True,
            "already_linked": False,
            "alumno": _alumno_to_dict(a),
        },
        status=200,
    )


@csrf_exempt
@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def cursos_disponibles(request):
    """
    GET /alumnos/cursos/
    Devuelve todos los cursos disponibles (catalogo Alumno.CURSOS).
    """
    # Preferimos los cursos reales en DB (para no listar cursos inexistentes).
    # Si no hay alumnos, caemos al catálogo definido en el modelo.
    catalogo = filtrar_cursos_validos(getattr(Alumno, "CURSOS", []))
    catalogo_ids = [c[0] for c in catalogo]

    try:
        reales = list(
            Alumno.objects.values_list("curso", flat=True).distinct().order_by("curso")
        )
    except Exception:
        reales = []

    if reales:
        reales_set = {str(c) for c in reales if c}
        ordered = [cid for cid in catalogo_ids if cid in reales_set]
        extras = sorted([cid for cid in reales_set if cid not in set(ordered)])
        cursos = [{"id": cid, "nombre": dict(catalogo).get(cid, cid)} for cid in (ordered + extras)]
    else:
        cursos = [{"id": c[0], "nombre": c[1]} for c in catalogo]
    return Response({"cursos": cursos}, status=200)


@csrf_exempt
@api_view(["POST"])
@parser_classes([JSONParser])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def transferir_alumno(request):
    """
    POST /alumnos/transferir/
    JSON:
      {
        "alumno_id": 123,   # opcional si envias id_alumno
        "id_alumno": "1A002",
        "curso": "2A"
      }
    """
    data = request.data or {}
    curso = (data.get("curso") or "").strip()

    if not _is_preceptor_user(request.user):
        return Response({"detail": "No autorizado."}, status=403)

    if not curso:
        return Response({"detail": "Falta el campo requerido: curso."}, status=400)
    if not _is_valid_curso(curso):
        return Response({"detail": f"Curso inválido: {curso}."}, status=400)

    alumno = _resolve_alumno_for_transfer(data)
    if not alumno:
        return Response({"detail": "Alumno no encontrado."}, status=404)

    # Si existe PreceptorCurso, validamos acceso al curso actual del alumno
    if PreceptorCurso is not None:
        try:
            if not PreceptorCurso.objects.filter(
                preceptor=request.user,
                curso=alumno.curso,
            ).exists():
                return Response({"detail": "No autorizado para ese alumno."}, status=403)
        except Exception:
            return Response({"detail": "No autorizado para ese alumno."}, status=403)

    if alumno.curso == curso:
        return Response(
            {
                "ok": True,
                "alumno": _alumno_to_dict(alumno),
                "message": "El alumno ya pertenece a ese curso.",
            },
            status=200,
        )

    alumno.curso = curso
    alumno.save(update_fields=["curso"])

    return Response(
        {
            "ok": True,
            "alumno": _alumno_to_dict(alumno),
        },
        status=200,
    )
