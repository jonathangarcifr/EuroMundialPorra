from django.db import models


class Apuesta(models.Model):
    nombre = models.CharField(max_length=100)
    email = models.EmailField()
    pagado = models.BooleanField(default=False)

    equipo_1 = models.CharField(max_length=100)
    equipo_2 = models.CharField(max_length=100)
    equipo_3 = models.CharField(max_length=100)
    equipo_4 = models.CharField(max_length=100)
    equipo_5 = models.CharField(max_length=100)
    equipo_6 = models.CharField(max_length=100)
    equipo_7 = models.CharField(max_length=100)
    equipo_8 = models.CharField(max_length=100)
    equipo_9 = models.CharField(max_length=100)
    equipo_10 = models.CharField(max_length=100)
    equipo_11 = models.CharField(max_length=100)
    equipo_12 = models.CharField(max_length=100)

    goleador = models.CharField(max_length=100)
    equipo_goleador = models.CharField(max_length=100)

    validacion = models.TextField(blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nombre} - {self.email}"
    

class Partido(models.Model):
    FASES = [
        ("J1", "Jornada 1"),
        ("J2", "Jornada 2"),
        ("J3", "Jornada 3"),
        ("1/16", "1/16 de final"),
        ("1/8", "1/8 de final"),
        ("1/4", "1/4 de final"),
        ("1/2", "1/2 de final"),
        ("FINAL", "Final"),
    ]

    fase = models.CharField(max_length=10, choices=FASES)
    grupo = models.CharField(max_length=20, blank=True, null=True)
    fecha_partido = models.DateTimeField(null=True, blank=True)

    equipo_local = models.CharField(max_length=100)
    equipo_visitante = models.CharField(max_length=100)

    goles_local = models.IntegerField(default=0)
    goles_visitante = models.IntegerField(default=0)

    jugado = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.equipo_local} vs {self.equipo_visitante}"
    

class GoleadorPartido(models.Model):
    partido = models.ForeignKey(
        Partido,
        on_delete=models.CASCADE,
        related_name="goleadores"
    )

    jugador = models.CharField(max_length=100)
    equipo = models.CharField(max_length=100)

    goles = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.jugador} ({self.equipo})"


class GoleadorTorneo(models.Model):
    jugador = models.CharField(max_length=100)
    equipo = models.CharField(max_length=100)
    goles = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("jugador", "equipo")

    def __str__(self):
        return f"{self.jugador} - {self.equipo}"
    
class GoleadorTorneo(models.Model):
    jugador = models.CharField(max_length=100)
    equipo = models.CharField(max_length=100)
    puntos = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True)

    class Meta:
        unique_together = ("jugador", "equipo")

    def __str__(self):
        return f"{self.jugador} - {self.equipo} ({self.puntos})"