# calificaciones/mi_curso.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

try:
    from .models import Alumno  # type: ignore
except Exception:
    Alumno = None


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def mi_curso(request):
    """
    Devuelve el curso del alumno logueado de forma sólida (OneToOne Alumno.user).

    Respuesta:
      {"curso": "1A"}  o  {"curso": ""} si no está linkeado.
    """
    if Alumno is None:
        return Response({"curso": ""}, status=status.HTTP_200_OK)

    # 1) Camino ideal: related_name="alumno"
    try:
        a = getattr(request.user, "alumno", None)
        if a is not None:
            curso = (getattr(a, "curso", "") or "").strip()
            return Response({"curso": curso}, status=status.HTTP_200_OK)
    except Exception:
        pass

    # 2) Fallback por si aún no linkeaste: username == id_alumno
    try:
        username = (getattr(request.user, "username", "") or "").strip()
        if username:
            a = Alumno.objects.filter(id_alumno=username).first()
            if a:
                curso = (getattr(a, "curso", "") or "").strip()
                return Response({"curso": curso}, status=status.HTTP_200_OK)
    except Exception:
        pass

    return Response({"curso": ""}, status=status.HTTP_200_OK)
