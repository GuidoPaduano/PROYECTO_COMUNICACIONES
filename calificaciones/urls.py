from django.urls import path, include
from . import views
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'eventos', views.EventoViewSet)

urlpatterns = [
    path('', views.index, name='index'),
    path('agregar_nota/', views.agregar_nota, name='agregar_nota'),
    path('boletin_pdf/<int:alumno_id>/', views.generar_boletin_pdf, name='boletin_pdf'),
    path('enviar_mensaje/', views.enviar_mensaje, name='enviar_mensaje'),
    path('mensajes/', views.ver_mensajes, name='ver_mensajes'),
    path('enviar_comunicado/', views.enviar_comunicado, name='enviar_comunicado'),
    path('ver_notas/', views.ver_notas, name='ver_notas'),
    path('historial/alumno/<str:alumno_id>/', views.historial_notas_profesor, name='historial_notas_profesor'),
    path('historial/', views.historial_notas_padre, name='historial_notas_padre'),
    path('calendario/', views.calendario_view, name='calendario'),
    path('crear_evento/', views.crear_evento, name='crear_evento'),
    path('eventos/editar/<int:evento_id>/', views.editar_evento, name='editar_evento'),
    path('eventos/eliminar/<int:evento_id>/', views.eliminar_evento, name='eliminar_evento'),
    path('api/', include(router.urls)),
]
