from django.contrib import admin
from .models import Apuesta
from .models import Partido, GoleadorPartido


@admin.register(Apuesta)
class ApuestaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "email", "pagado", "goleador", "equipo_goleador", "fecha_creacion")
    search_fields = ("nombre", "email", "goleador")
    list_filter = ("pagado",)


@admin.register(Partido)
class PartidoAdmin(admin.ModelAdmin):
    list_display = (
        "fase",
        "equipo_local",
        "equipo_visitante",
        "goles_local",
        "goles_visitante",
        "jugado",
    )

    list_filter = ("fase", "jugado")


@admin.register(GoleadorPartido)
class GoleadorPartidoAdmin(admin.ModelAdmin):
    list_display = (
        "partido",
        "jugador",
        "equipo",
        "goles",
    )