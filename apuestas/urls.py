from django.urls import path
from . import views

urlpatterns = [
    path("", views.cuentaatras, name="home"),
    path("inicio/", views.inicio, name="inicio"),
    path("nueva/", views.nueva_apuesta, name="nueva_apuesta"),
    path("apuestas/", views.ver_apuestas, name="ver_apuestas"),
    path("apuestas/<int:apuesta_id>/editar/", views.editar_apuesta, name="editar_apuesta"),
    path("resultados/", views.resultados, name="resultados"),
    path("clasificacion/", views.clasificacion, name="clasificacion"),
    path("clasificacion/pdf/", views.exportar_clasificacion_pdf, name="exportar_clasificacion_pdf"),
    path("puntuaciones/", views.puntuaciones, name="puntuaciones"),
    path("cuentaatras/",views.cuentaatras,name="cuentaatras",
         ),
]