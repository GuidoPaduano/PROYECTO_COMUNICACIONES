# calificaciones/serializers.py
from decimal import Decimal, InvalidOperation

from django.apps import apps
from rest_framework import serializers

from .models import Alumno, Evento, Nota, Sancion, validate_calificacion_ext


_ESTADOS = {"TEA", "TEP", "TED"}


def _parse_nota_numerica(value):
    if value in (None, ""):
        return None
    try:
        parsed = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if parsed < Decimal("1") or parsed > Decimal("10"):
        return None
    return parsed.quantize(Decimal("0.01"))


def _format_nota_numerica(value):
    parsed = _parse_nota_numerica(value)
    if parsed is None:
        return ""
    txt = f"{parsed:.2f}"
    return txt.rstrip("0").rstrip(".")


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

    Soporta esquema nuevo:
    - resultado: TEA/TEP/TED (principal)
    - nota_numerica: opcional

    Compatibilidad legacy:
    - calificacion (texto) sigue siendo aceptada.
    """

    alumno = serializers.PrimaryKeyRelatedField(queryset=Alumno.objects.all())
    calificacion = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    resultado = serializers.ChoiceField(
        choices=Nota.RESULTADO_CHOICES,
        required=False,
        allow_null=True,
    )
    nota_numerica = serializers.DecimalField(
        max_digits=4,
        decimal_places=2,
        required=False,
        allow_null=True,
    )
    fecha = serializers.DateField(required=False, allow_null=True)
    observaciones = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = Nota
        fields = [
            "alumno",
            "materia",
            "tipo",
            "calificacion",
            "resultado",
            "nota_numerica",
            "cuatrimestre",
            "fecha",
            "observaciones",
        ]

    def validate_calificacion(self, value):
        v = str(value or "").strip()
        if not v:
            return ""
        v_up = v.upper()
        validate_calificacion_ext(v_up)
        return v_up

    def validate_resultado(self, value):
        if value in (None, ""):
            return None
        return str(value).upper()

    def validate_cuatrimestre(self, value):
        try:
            iv = int(value)
        except Exception:
            raise serializers.ValidationError("El cuatrimestre debe ser 1 o 2.")
        if iv not in (1, 2):
            raise serializers.ValidationError("El cuatrimestre debe ser 1 o 2.")
        return iv

    def validate(self, attrs):
        current_calificacion = getattr(self.instance, "calificacion", "") if self.instance else ""
        current_resultado = getattr(self.instance, "resultado", None) if self.instance else None
        current_nota_numerica = getattr(self.instance, "nota_numerica", None) if self.instance else None

        calificacion = str(attrs.get("calificacion", current_calificacion) or "").strip().upper()
        resultado = attrs.get("resultado", current_resultado)
        nota_numerica = attrs.get("nota_numerica", current_nota_numerica)

        if calificacion:
            # Compatibilidad: si calificacion legacy trae TEA/TEP/TED, poblar resultado
            if calificacion in _ESTADOS and not resultado:
                attrs["resultado"] = calificacion
                resultado = calificacion

            # Compatibilidad: si calificacion legacy es numerica, poblar nota_numerica
            parsed_num = _parse_nota_numerica(calificacion)
            if parsed_num is not None and nota_numerica is None:
                attrs["nota_numerica"] = parsed_num
                nota_numerica = parsed_num

            attrs["calificacion"] = calificacion
        else:
            attrs["calificacion"] = ""

        if resultado is None and nota_numerica is None and not attrs.get("calificacion"):
            raise serializers.ValidationError(
                "Debes informar resultado, nota_numerica o calificacion."
            )

        # Mantener calificacion legacy poblada para no romper flujos existentes.
        if not attrs.get("calificacion"):
            if resultado:
                attrs["calificacion"] = str(resultado).upper()
            elif nota_numerica is not None:
                attrs["calificacion"] = _format_nota_numerica(nota_numerica)

        return attrs

    def create(self, validated_data):
        fecha = validated_data.pop("fecha", None)
        nota = Nota(**validated_data)
        if fecha is not None:
            try:
                nota.fecha = fecha
            except Exception:
                pass
        nota.full_clean()
        nota.save()
        return nota

    def update(self, instance, validated_data):
        fecha = validated_data.pop("fecha", None)
        update_fields = []
        for key, value in validated_data.items():
            setattr(instance, key, value)
            update_fields.append(key)
        if fecha is not None:
            try:
                instance.fecha = fecha
                update_fields.append("fecha")
            except Exception:
                pass
        if update_fields:
            instance.save(update_fields=list(dict.fromkeys(update_fields)))
        else:
            instance.save()
        return instance


class NotaSerializer(serializers.ModelSerializer):
    """
    Para lecturas/listados de notas.
    """

    alumno = AlumnoSerializer(read_only=True)
    calificacion_display = serializers.CharField(source="get_calificacion_display", read_only=True)
    resultado_display = serializers.SerializerMethodField()

    class Meta:
        model = Nota
        fields = [
            "id",
            "alumno",
            "materia",
            "tipo",
            "calificacion",
            "calificacion_display",
            "resultado",
            "resultado_display",
            "nota_numerica",
            "cuatrimestre",
            "fecha",
            "observaciones",
            "firmada",
            "firmada_en",
        ]

    def get_resultado_display(self, obj):
        return obj.get_resultado_display() if obj.resultado else None


class EventoSerializer(serializers.ModelSerializer):
    """
    Serializer para Evento (API de calendario).
    - Normaliza valores vacios de la UI ("" -> None) para curso/tipo_evento/descripcion.
    - 'creado_por' solo lectura; lo setea la vista.
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
        allowed = {str(c[0]) for c in Evento._meta.get_field("tipo_evento").choices}
        if v not in allowed:
            raise serializers.ValidationError("tipo_evento invalido.")
        return v

    def validate_descripcion(self, v):
        return v


class AlumnoFullSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alumno
        fields = ["id", "id_alumno", "nombre", "apellido", "curso"]


class NotaPublicSerializer(serializers.ModelSerializer):
    calificacion_display = serializers.CharField(source="get_calificacion_display", read_only=True)
    resultado_display = serializers.SerializerMethodField()

    class Meta:
        model = Nota
        fields = (
            "id",
            "materia",
            "tipo",
            "calificacion",
            "calificacion_display",
            "resultado",
            "resultado_display",
            "nota_numerica",
            "cuatrimestre",
            "fecha",
            "observaciones",
            "firmada",
            "firmada_en",
        )

    def get_resultado_display(self, obj):
        return obj.get_resultado_display() if obj.resultado else None


SancionModel = apps.get_model("calificaciones", "Sancion")


class SancionPublicSerializer(serializers.ModelSerializer):
    """Serializer compatible con frontend legacy y moderno."""

    alumno_id = serializers.IntegerField(source="alumno.id", read_only=True)
    alumno_nombre = serializers.SerializerMethodField()

    curso = serializers.SerializerMethodField()

    # Campos legacy
    asunto = serializers.SerializerMethodField()
    mensaje = serializers.SerializerMethodField()
    creado_por = serializers.SerializerMethodField()
    creado_en = serializers.SerializerMethodField()

    # Campos consistentes
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
            "motivo",
            "docente",
            "asunto",
            "mensaje",
            "creado_por",
            "creado_en",
            "firmada",
            "firmada_en",
        ]

    def get_alumno_nombre(self, obj):
        nm = (getattr(obj.alumno, "nombre", "") or "").strip()
        ap = (getattr(obj.alumno, "apellido", "") or "").strip()
        full = (f"{nm} {ap}").strip()
        return full or nm or str(getattr(obj.alumno, "id", ""))

    def get_curso(self, obj):
        return getattr(getattr(obj, "alumno", None), "curso", None)

    def get_asunto(self, obj):
        det = (getattr(obj, "detalle", "") or "").strip()
        if det:
            return det
        return (getattr(obj, "tipo", "") or "").strip() or "-"

    def get_mensaje(self, obj):
        return (getattr(obj, "motivo", "") or "").strip() or "-"

    def get_motivo(self, obj):
        return self.get_mensaje(obj)

    def get_creado_por(self, obj):
        return (getattr(obj, "docente", "") or "").strip() or None

    def get_docente(self, obj):
        return self.get_creado_por(obj)

    def get_creado_en(self, obj):
        try:
            f = getattr(obj, "fecha", None)
            return f.isoformat() if f else None
        except Exception:
            return None
