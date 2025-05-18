from rest_framework import serializers
from .models import Evento

class EventoSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source='titulo')
    start = serializers.SerializerMethodField()
    description = serializers.CharField(source='descripcion')
    allDay = serializers.SerializerMethodField()  # 👈 este campo nuevo

    class Meta:
        model = Evento
        fields = ['id', 'title', 'start', 'description', 'curso', 'tipo_evento', 'allDay']

    def get_start(self, obj):
        return f"{obj.fecha}T00:00:00"

    def get_allDay(self, obj):
        return True


