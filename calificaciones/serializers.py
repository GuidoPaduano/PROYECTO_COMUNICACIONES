# calificaciones/serializers.py
from rest_framework import serializers
from .models import Alumno, Nota, Evento, Sancion
from .validators import validate_calificacion
from django.apps import apps



class AlumnoSerializer(serializers.ModelSerializer):
    """
    Usado para /calificaciones/nueva-nota/datos/ (Next.js).
    """
    class Meta:
        model = Alumno
        fields = ["id", "id_alumno", "nombre", "apellido", "curso"]


class NotaCreateSerializer(serializers.ModelSerializer):
    """
    Crear Nota desde API.
    Acepta:
      - Numéricas "1"…"10"
      - TEA / TEP / TED
      - NO ENTREGADO (también si llega como "No entregado")
    """
    alumno = serializers.PrimaryKeyRelatedField(queryset=Alumno.objects.all())
    fecha = serializers.DateField(required=False, allow_null=True)

    class Meta:
        model = Nota
        fields = ["alumno", "materia", "tipo", "calificacion", "cuatrimestre", "fecha"]

    def validate_calificacion(self, value):
        v = str(value or "").strip()
        if not v:
            raise serializers.ValidationError("Calificación requerida.")

        v_up = v.upper()

        # Aceptar “No entregado” en cualquier capitalización
        if v_up == "NO ENTREGADO":
            return "NO ENTREGADO"

        # Delegar validación estándar (1–10, TEA/TEP/TED)
        validate_calificacion(v_up)
        return v_up

    def validate_cuatrimestre(self, value):
        try:
            iv = int(value)
        except Exception:
            raise serializers.ValidationError("El cuatrimestre debe ser 1 o 2.")
        if iv not in (1, 2):
            raise serializers.ValidationError("El cuatrimestre debe ser 1 o 2.")
        return iv

    def create(self, validated_data):
        fecha = validated_data.pop("fecha", None)
        nota = Nota(**validated_data)
        if fecha is not None:
            try:
                nota.fecha = fecha
            except Exception:
                # si no parsea, dejamos que el modelo maneje fecha
                pass
        nota.full_clean()
        nota.save()
        return nota


class NotaSerializer(serializers.ModelSerializer):
    """
    Para lecturas/listados de notas.
    """
    alumno = AlumnoSerializer(read_only=True)
    calificacion_display = serializers.CharField(source="get_calificacion_display", read_only=True)

    class Meta:
        model = Nota
        fields = [
            "id",
            "alumno",
            "materia",
            "tipo",
            "calificacion",
            "calificacion_display",  # ⬅️ etiqueta legible (incluye "No entregado")
            "cuatrimestre",
            "fecha",
        ]


class EventoSerializer(serializers.ModelSerializer):
    """
    Serializer para Evento (API de calendario).
    - Normaliza valores vacíos de la UI ("" -> None) para curso/tipo_evento/descripcion.
    - 'creado_por' solo lectura; lo setea la vista.
    - Valida tipo_evento contra choices del modelo (sin desincronizarse).
    """
    titulo = serializers.CharField(required=True, allow_blank=False, trim_whitespace=True)
    descripcion = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    fecha = serializers.DateField(required=True, input_formats=["%Y-%m-%d"])
    curso = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    tipo_evento = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    creado_por = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Evento
        fields = ["id", "titulo", "descripcion", "fecha", "curso", "tipo_evento", "creado_por"]
        read_only_fields = ["creado_por"]

    def validate_curso(self, v):
        if v in ("", None):
            return None
        return v

    def validate_tipo_evento(self, v):
        if v in ("", None):
            return None
        allowed = {c[0] for c in Evento.TIPOS_EVENTO}  # p.ej. {'evaluacion','entrega','otro'}
        if v not in allowed:
            raise serializers.ValidationError("tipo_evento inválido.")
        return v

    def validate_descripcion(self, v):
        return v


# --------------------------------------------------------------------
# Serializers adicionales usados por vistas/lecturas específicas
# --------------------------------------------------------------------
class AlumnoFullSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alumno
        fields = [
            "id", "id_alumno", "nombre", "apellido", "curso",
        ]


class NotaPublicSerializer(serializers.ModelSerializer):
    calificacion_display = serializers.CharField(source="get_calificacion_display", read_only=True)

    class Meta:
        model = Nota
        fields = (
            "id",
            "materia",
            "tipo",
            "calificacion",
            "calificacion_display",  # ⬅️ etiqueta legible para front público
            "cuatrimestre",
            "fecha",
        )

        # --- Sanciones ---
SancionModel = apps.get_model("calificaciones", "Sancion")

class SancionPublicSerializer(serializers.ModelSerializer):
    """Serializer *compatible* con el frontend legacy.

    Modelo actual (calificaciones.Sancion):
      - motivo (TextField)  -> frontend: mensaje
      - detalle (TextField) -> frontend: asunto
      - fecha (DateField)
      - tipo (CharField)
      - docente (CharField)

    Salida mantiene: curso/asunto/mensaje/creado_por/creado_en
    para no romper pantallas ya existentes.
    """
    alumno_id = serializers.IntegerField(source="alumno.id", read_only=True)
    alumno_nombre = serializers.SerializerMethodField()

    curso = serializers.SerializerMethodField()

    # Campos legacy (mantener para no romper pantallas viejas)
    asunto = serializers.SerializerMethodField()
    mensaje = serializers.SerializerMethodField()
    creado_por = serializers.SerializerMethodField()
    creado_en = serializers.SerializerMethodField()

    # Campos NUEVOS y consistentes para el frontend moderno
    # (así no dependemos de alias como creado_por/mensaje)
    motivo = serializers.SerializerMethodField()
    docente = serializers.SerializerMethodField()

    class Meta:
        model = SancionModel
        fields = [
            "id",
            "alumno_id",
            "alumno_nombre",
            "curso",
            "fecha",
            # consistentes
            "motivo",
            "docente",
            "asunto",
            "mensaje",
            "creado_por",
            "creado_en",
        ]

    def get_alumno_nombre(self, obj):
        nm = (getattr(obj.alumno, "nombre", "") or "").strip()
        ap = (getattr(obj.alumno, "apellido", "") or "").strip()
        full = (f"{nm} {ap}").strip()
        return full or nm or str(getattr(obj.alumno, "id", ""))

    def get_curso(self, obj):
        return getattr(getattr(obj, "alumno", None), "curso", None)

    def get_asunto(self, obj):
        # Preferimos detalle (lo que el usuario escribió como “asunto”).
        det = (getattr(obj, "detalle", "") or "").strip()
        if det:
            return det
        # Fallback a tipo (Amonestación/Suspensión/etc.)
        return (getattr(obj, "tipo", "") or "").strip() or "—"

    def get_mensaje(self, obj):
        return (getattr(obj, "motivo", "") or "").strip() or "—"

    def get_motivo(self, obj):
        # Alias consistente: motivo == mensaje
        return self.get_mensaje(obj)

    def get_creado_por(self, obj):
        return (getattr(obj, "docente", "") or "").strip() or None

    def get_docente(self, obj):
        # Alias consistente: docente == creado_por
        return self.get_creado_por(obj)

    def get_creado_en(self, obj):
        # No existe created_at en Sancion actual; devolvemos fecha como compat.
        try:
            f = getattr(obj, "fecha", None)
            return f.isoformat() if f else None
        except Exception:
            return None
