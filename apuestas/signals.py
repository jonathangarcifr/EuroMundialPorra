from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Apuesta, GoleadorPartido, Partido, GoleadorTorneo


def limpiar_cache_clasificacion():
    cache.delete_many([
        "equipos_eliminados",
        "resumen_ideal_cuchara",
        "clasificacion_completa_v1",
    ])


@receiver([post_save, post_delete], sender=Partido)
def limpiar_cache_partido(sender, instance, **kwargs):
    limpiar_cache_clasificacion()


@receiver([post_save, post_delete], sender=GoleadorPartido)
def limpiar_cache_goleador_partido(sender, instance, **kwargs):
    limpiar_cache_clasificacion()


@receiver([post_save, post_delete], sender=Apuesta)
def limpiar_cache_apuesta(sender, instance, **kwargs):
    limpiar_cache_clasificacion()


@receiver([post_save, post_delete], sender=GoleadorTorneo)
def limpiar_cache_goleador_torneo(sender, instance, **kwargs):
    limpiar_cache_clasificacion()