from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.db.models import Prefetch
from django.db.models.functions import Lower
from .models import Partido, Apuesta, GoleadorPartido
from .forms import ApuestaForm, PartidoForm
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from .choices import TODOS_EQUIPOS, EQUIPOS_INFO, BOMBO_1, BOMBO_2, BOMBO_3, BOMBO_4, BOMBO_5, BOMBO_6

def inicio(request):
    return render(request, "apuestas/inicio.html")


@staff_member_required
def nueva_apuesta(request):
    if request.method == "POST":
        form = ApuestaForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("ver_apuestas")
    else:
        form = ApuestaForm()

    return render(request, "apuestas/formulario_apuesta.html", {"form": form})

def obtener_info_equipo(nombre):
    info = EQUIPOS_INFO.get(nombre, {})
    return {
        "nombre": nombre,
        "codigo": info.get("codigo", nombre[:3].upper()),
        "flag": info.get("flag", ""),
    }


def ver_apuestas(request):
    import unicodedata

    apuestas = sorted(
        Apuesta.objects.all(),
        key=lambda a: unicodedata.normalize("NFKD", a.nombre)
        .encode("ASCII", "ignore")
        .decode("ASCII")
        .lower()
    )

    leyenda = [
        obtener_info_equipo(nombre)
        for nombre, _ in TODOS_EQUIPOS
    ]

    apuestas_preparadas = []

    for apuesta in apuestas:
        equipos = [
            obtener_info_equipo(getattr(apuesta, f"equipo_{i}"))
            for i in range(1, 13)
        ]

        apuestas_preparadas.append({
            "apuesta": apuesta,
            "equipos": equipos,
            "equipo_goleador_info": obtener_info_equipo(apuesta.equipo_goleador),
        })

    return render(
        request,
        "apuestas/ver_apuestas.html",
        {
            "leyenda": leyenda,
            "apuestas_preparadas": apuestas_preparadas,
        }
    )


@staff_member_required
def editar_apuesta(request, apuesta_id):
    apuesta = get_object_or_404(Apuesta, id=apuesta_id)

    if request.method == "POST":
        form = ApuestaForm(request.POST, instance=apuesta)
        if form.is_valid():
            form.save()
            return redirect("ver_apuestas")
    else:
        form = ApuestaForm(instance=apuesta)

    return render(request, "apuestas/formulario_apuesta.html", {"form": form})


def sincronizar_goleadores_partidos():
    apuestas_goleadores = list(
        Apuesta.objects
        .exclude(goleador="")
        .exclude(equipo_goleador="")
        .values("goleador", "equipo_goleador")
        .distinct()
    )

    partidos = list(
        Partido.objects
        .all()
        .only("id", "equipo_local", "equipo_visitante")
    )

    existentes = set(
        GoleadorPartido.objects.values_list(
            "partido_id",
            "jugador",
            "equipo"
        )
    )

    nuevos = []
    nuevos_keys = set()

    for partido in partidos:
        equipos_partido = [partido.equipo_local, partido.equipo_visitante]

        for apuesta in apuestas_goleadores:
            jugador = apuesta["goleador"]
            equipo = apuesta["equipo_goleador"]

            if equipo not in equipos_partido:
                continue

            key = (partido.id, jugador, equipo)

            if key in existentes or key in nuevos_keys:
                continue

            nuevos.append(
                GoleadorPartido(
                    partido=partido,
                    jugador=jugador,
                    equipo=equipo,
                    goles=0,
                )
            )

            nuevos_keys.add(key)

    if nuevos:
        GoleadorPartido.objects.bulk_create(nuevos)


def resultados(request):
    partido_form = PartidoForm()

    if request.method == "POST" and not request.user.is_staff:
        return redirect("resultados")

    if request.method == "POST":
        tipo_formulario = request.POST.get("tipo_formulario")

        if tipo_formulario == "nuevo_partido":
            partido_form = PartidoForm(request.POST)

            if partido_form.is_valid():
                nuevo_partido = partido_form.save()
                sincronizar_goleadores_partidos()
                return redirect(f"{reverse('resultados')}?fase={nuevo_partido.fase}")

        else:
            partido_id = request.POST.get("partido_id")
            accion = request.POST.get("accion")

            partido = get_object_or_404(Partido, id=partido_id)

            if accion == "editar":
                partido.jugado = False
                partido.save()
                return redirect(f"{reverse('resultados')}?fase={partido.fase}")

            if accion == "confirmar":
                goleadores_ids = request.POST.getlist("goleador_id")

                for goleador_id in goleadores_ids:
                    valor = request.POST.get(f"goles_goleador_{goleador_id}")

                    if valor == "" or valor is None:
                        return redirect(f"{reverse('resultados')}?fase={partido.fase}")

                partido.goles_local = int(request.POST.get("goles_local", 0))
                partido.goles_visitante = int(request.POST.get("goles_visitante", 0))
                partido.jugado = True
                partido.save()

                for goleador_id in goleadores_ids:
                    goles = int(request.POST.get(f"goles_goleador_{goleador_id}", 0))
                    goleador = get_object_or_404(GoleadorPartido, id=goleador_id)
                    goleador.goles = goles
                    goleador.save()

                return redirect(f"{reverse('resultados')}?fase={partido.fase}")

    sincronizar_goleadores_partidos()

    jornadas = []

    for codigo_fase, nombre_fase in Partido.FASES:
        partidos_fase = (
            Partido.objects
            .filter(fase=codigo_fase)
            .prefetch_related(
                Prefetch(
                    "goleadores",
                    queryset=GoleadorPartido.objects.order_by("jugador"),
                    to_attr="goleadores_prefetch"
                )
            )
            .order_by("fecha_partido", "id")
        )

        partidos_preparados = []

        for partido in partidos_fase:
            goleadores_local = [
                g for g in partido.goleadores_prefetch
                if g.equipo == partido.equipo_local
            ]

            goleadores_visitante = [
                g for g in partido.goleadores_prefetch
                if g.equipo == partido.equipo_visitante
            ]

            partidos_preparados.append({
                "partido": partido,
                "local_info": obtener_info_equipo(partido.equipo_local),
                "visitante_info": obtener_info_equipo(partido.equipo_visitante),
                "goleadores_local": goleadores_local,
                "goleadores_visitante": goleadores_visitante,
                "total_goleadores": len(goleadores_local) + len(goleadores_visitante),
            })

        if partidos_preparados:
            jornadas.append({
                "codigo": codigo_fase,
                "nombre": nombre_fase,
                "partidos": partidos_preparados,
            })

    fase_activa = request.GET.get("fase")

    if not fase_activa and jornadas:
        fase_activa = jornadas[0]["codigo"]

    return render(
        request,
        "apuestas/resultados.html",
        {
            "jornadas": jornadas,
            "partido_form": partido_form,
            "fase_activa": fase_activa,
        }
    )


def clasificacion(request):
    import unicodedata

    apuestas = sorted(
        Apuesta.objects.all(),
        key=lambda a: unicodedata.normalize("NFKD", a.nombre)
        .encode("ASCII", "ignore")
        .decode("ASCII")
        .lower()
    )

    clasificacion_data = []

    for apuesta in apuestas:
        (
            puntos_equipos,
            puntos_goleador,
            puntos_totales,
            detalle_equipos,
        ) = calcular_puntos_apuesta(apuesta)

        equipos = []

        for i in range(1, 13):
            nombre_equipo = getattr(apuesta, f"equipo_{i}")
            info = obtener_info_equipo(nombre_equipo)
            equipos.append(info)

        clasificacion_data.append({
            "apuesta": apuesta,
            "equipos": equipos,
            "equipo_goleador_info": obtener_info_equipo(
                apuesta.equipo_goleador
            ),
            "puntos_equipos": puntos_equipos,
            "puntos_goleador": puntos_goleador,
            "puntos_totales": puntos_totales,
            "puntos_display": (
                f"{puntos_equipos + puntos_goleador}"
                f".{puntos_goleador:02d}"
            ),
        })

    clasificacion_data.sort(
        key=lambda x: (
            -x["puntos_totales"],
            x["apuesta"].nombre.lower(),
        )
    )

    posicion = 0
    posicion_real = 0
    puntos_anteriores = None

    for item in clasificacion_data:
        posicion += 1

        if puntos_anteriores != item["puntos_totales"]:
            posicion_real = posicion

        item["posicion"] = posicion_real

        puntos_anteriores = item["puntos_totales"]

    resumen_ideal_cuchara = obtener_resumen_ideal_cuchara()

    return render(
        request,
        "apuestas/clasificacion.html",
        {
            "clasificacion": clasificacion_data,
            "resumen_ideal_cuchara": resumen_ideal_cuchara,
        }
    )

def obtener_datos_clasificacion():
    apuestas = Apuesta.objects.all()

    clasificacion_data = []

    for apuesta in apuestas:
        (
            puntos_equipos,
            puntos_goleador,
            puntos_totales,
            detalle_equipos,
        ) = calcular_puntos_apuesta(apuesta)

        equipos = []

        for i in range(1, 13):
            nombre_equipo = getattr(apuesta, f"equipo_{i}")
            info = obtener_info_equipo(nombre_equipo)
            equipos.append(info)

        clasificacion_data.append({
            "apuesta": apuesta,
            "equipos": equipos,
            "puntos_totales": puntos_totales,
            "equipo_goleador_info": obtener_info_equipo(apuesta.equipo_goleador),
            "puntos_display": (
                f"{puntos_equipos + puntos_goleador}"
                f".{puntos_goleador:02d}"
            ),
        })

    clasificacion_data.sort(
        key=lambda x: (
            -x["puntos_totales"],
            x["apuesta"].nombre.lower(),
        )
    )

    return clasificacion_data

PUNTOS_FASE = {
    "J1": {"victoria": 3, "empate": 2, "derrota": 1},
    "J2": {"victoria": 3, "empate": 2, "derrota": 1},
    "J3": {"victoria": 3, "empate": 2, "derrota": 1},
    "1/16": {"victoria": 4, "derrota": 2},
    "1/8": {"victoria": 6, "derrota": 3},
    "1/4": {"victoria": 8, "derrota": 4},
    "1/2": {"victoria": 10, "derrota": 5},
    "FINAL": {"victoria": 20, "derrota": 10},
}

PUNTOS_GOLEADOR = {
    "J1": 1,
    "J2": 1,
    "J3": 1,
    "1/16": 2,
    "1/8": 3,
    "1/4": 4,
    "1/2": 5,
    "FINAL": 10,
}

FASE_TEMPLATE = {
    "J1": "J1",
    "J2": "J2",
    "J3": "J3",
    "1/16": "DIEC",
    "1/8": "OCT",
    "1/4": "CUA",
    "1/2": "SEM",
    "FINAL": "FINAL",
}

def crear_diccionario_fases():
    return {
        "J1": {"valor": 0, "activa": False},
        "J2": {"valor": 0, "activa": False},
        "J3": {"valor": 0, "activa": False},
        "DIEC": {"valor": 0, "activa": False},
        "OCT": {"valor": 0, "activa": False},
        "CUA": {"valor": 0, "activa": False},
        "SEM": {"valor": 0, "activa": False},
        "FINAL": {"valor": 0, "activa": False},
    }


def calcular_puntuaciones_globales():
    puntos_equipos = {}
    puntos_goleadores = {}

    partidos = (
        Partido.objects
        .filter(jugado=True)
        .prefetch_related("goleadores")
        .order_by("fecha_partido", "id")
    )

    for partido in partidos:
        clave_fase = FASE_TEMPLATE.get(partido.fase)

        if not clave_fase:
            continue

        equipos_partido = [
            (
                partido.equipo_local,
                partido.goles_local,
                partido.goles_visitante,
            ),
            (
                partido.equipo_visitante,
                partido.goles_visitante,
                partido.goles_local,
            ),
        ]

        for equipo, goles_favor, goles_contra in equipos_partido:
            if equipo not in puntos_equipos:
                puntos_equipos[equipo] = crear_diccionario_fases()

            puntos_equipos[equipo][clave_fase]["activa"] = True

            puntos_partido = 0

            if goles_favor > goles_contra:
                puntos_partido += PUNTOS_FASE[partido.fase]["victoria"]
            elif goles_favor == goles_contra:
                puntos_partido += PUNTOS_FASE[partido.fase].get("empate", 0)
            else:
                puntos_partido += PUNTOS_FASE[partido.fase]["derrota"]

            puntos_partido += goles_favor

            puntos_equipos[equipo][clave_fase]["valor"] += puntos_partido

        for goleador in partido.goleadores.all():
            clave_goleador = (
                goleador.jugador,
                goleador.equipo,
            )

            if clave_goleador not in puntos_goleadores:
                puntos_goleadores[clave_goleador] = crear_diccionario_fases()

            puntos_goleadores[clave_goleador][clave_fase]["activa"] = True
            puntos_goleadores[clave_goleador][clave_fase]["valor"] += (
                goleador.goles * PUNTOS_GOLEADOR.get(partido.fase, 0)
            )

    for datos in puntos_equipos.values():
        datos["TOTAL"] = sum(
            datos[fase]["valor"]
            for fase in ["J1", "J2", "J3", "DIEC", "OCT", "CUA", "SEM", "FINAL"]
        )

    for datos in puntos_goleadores.values():
        datos["TOTAL"] = sum(
            datos[fase]["valor"]
            for fase in ["J1", "J2", "J3", "DIEC", "OCT", "CUA", "SEM", "FINAL"]
        )

    return puntos_equipos, puntos_goleadores


def calcular_puntos_apuesta(apuesta):
    equipos_apostados = [
        apuesta.equipo_1,
        apuesta.equipo_2,
        apuesta.equipo_3,
        apuesta.equipo_4,
        apuesta.equipo_5,
        apuesta.equipo_6,
        apuesta.equipo_7,
        apuesta.equipo_8,
        apuesta.equipo_9,
        apuesta.equipo_10,
        apuesta.equipo_11,
        apuesta.equipo_12,
    ]

    puntos_equipos = 0
    puntos_goleador = 0

    detalle_equipos = {}

    partidos = (
        Partido.objects
        .filter(jugado=True)
        .prefetch_related("goleadores")
        .order_by("fecha_partido", "id")
    )

    for partido in partidos:
        if partido.fase not in PUNTOS_FASE:
            continue

        for equipo in equipos_apostados:
            if equipo == partido.equipo_local:
                goles_favor = partido.goles_local
                goles_contra = partido.goles_visitante
            elif equipo == partido.equipo_visitante:
                goles_favor = partido.goles_visitante
                goles_contra = partido.goles_local
            else:
                continue

            if equipo not in detalle_equipos:
                detalle_equipos[equipo] = {
                    "total": 0,
                    "fases": {}
                }

            puntos_partido = 0

            if goles_favor > goles_contra:
                puntos_partido += PUNTOS_FASE[partido.fase]["victoria"]
            elif goles_favor == goles_contra:
                puntos_partido += PUNTOS_FASE[partido.fase].get("empate", 0)
            else:
                puntos_partido += PUNTOS_FASE[partido.fase]["derrota"]

            puntos_partido += goles_favor

            puntos_equipos += puntos_partido

            detalle_equipos[equipo]["total"] += puntos_partido
            detalle_equipos[equipo]["fases"][partido.fase] = (
                detalle_equipos[equipo]["fases"].get(partido.fase, 0)
                + puntos_partido
            )

        goles = partido.goleadores.filter(
            jugador__iexact=apuesta.goleador,
            equipo=apuesta.equipo_goleador,
        ).first()

        if goles:
            puntos_goleador += goles.goles * PUNTOS_GOLEADOR.get(partido.fase, 0)

    puntos_totales = (
        puntos_equipos
        + puntos_goleador
        + (puntos_goleador / 100)
    )

    return (
        puntos_equipos,
        puntos_goleador,
        puntos_totales,
        detalle_equipos,
    )

@staff_member_required
def exportar_clasificacion_pdf(request):
    clasificacion_data = obtener_datos_clasificacion()

    response = HttpResponse(content_type="application/pdf")

    fase_clasificacion = obtener_fase_clasificacion()    
    nombre_fichero = (
        f"EuroMundial_Porra_Clasificacion_{fase_clasificacion}.pdf"
    )

    response["Content-Disposition"] = (
        f'attachment; filename="{nombre_fichero}"'
    )

    doc = SimpleDocTemplate(
        response,
        pagesize=landscape(A4),
        rightMargin=6,
        leftMargin=6,
        topMargin=12,
        bottomMargin=12,
    )

    styles = getSampleStyleSheet()
    elementos = []

    titulo = Paragraph(
        f"<b>EuroMundial Porra - Clasificación - {fase_clasificacion}</b>",
        styles["Title"]
    )
    elementos.append(titulo)
    elementos.append(Spacer(1, 10))

    cabecera = [
        "Pos",
        "Nombre",
        "E1", "E2", "E3", "E4", "E5", "E6",
        "E7", "E8", "E9", "E10", "E11", "E12",
        "Goleador",
        "Puntos",
    ]

    datos = [cabecera]

    for posicion, item in enumerate(clasificacion_data, start=1):
        apuesta = item["apuesta"]

        fila = [
            str(posicion),
            apuesta.nombre,
        ]

        for equipo in item["equipos"]:
            fila.append(equipo["nombre"])

        fila.extend([
            f"{apuesta.goleador} - {apuesta.equipo_goleador}",
            item["puntos_display"],
        ])

        datos.append(fila)

    tabla = Table(
        datos,
        repeatRows=1,
        colWidths=[
            18,   # Pos
            62,   # Nombre
            45, 45, 45, 45, 45, 45,
            45, 45, 45, 45, 45, 45,
            105,  # Goleador
            35,   # Puntos
        ],
    )

    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.2),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (1, 1), (1, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d0d7de")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white,
            colors.HexColor("#f8fbfd"),
        ]),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (-1, 1), (-1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (-1, 1), (-1, -1), colors.HexColor("#0d6efd")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    elementos.append(tabla)

    doc.build(elementos)

    return response

def obtener_fase_clasificacion():
    fases = Partido.FASES

    ultima_fase_completa = None

    for codigo_fase, nombre_fase in fases:
        partidos_fase = Partido.objects.filter(fase=codigo_fase)

        if not partidos_fase.exists():
            continue

        todos_jugados = not partidos_fase.filter(jugado=False).exists()

        if todos_jugados:
            ultima_fase_completa = nombre_fase
        else:
            break

    return ultima_fase_completa or "Sin partidos finalizados"

def calcular_puntos_equipo_por_fase(nombre_equipo, puntos_equipos=None):
    if puntos_equipos is None:
        puntos_equipos, _ = calcular_puntuaciones_globales()

    puntos = puntos_equipos.get(nombre_equipo, crear_diccionario_fases())
    puntos["TOTAL"] = puntos.get("TOTAL", 0)

    return puntos


def calcular_puntos_goleador_por_fase(nombre_jugador, nombre_equipo, puntos_goleadores=None):
    if puntos_goleadores is None:
        _, puntos_goleadores = calcular_puntuaciones_globales()

    puntos = puntos_goleadores.get(
        (nombre_jugador, nombre_equipo),
        crear_diccionario_fases()
    )

    puntos["TOTAL"] = puntos.get("TOTAL", 0)

    return puntos


def puntuaciones(request):
    bombos = [
        ("Bombo 1", BOMBO_1),
        ("Bombo 2", BOMBO_2),
        ("Bombo 3", BOMBO_3),
        ("Bombo 4", BOMBO_4),
        ("Bombo 5", BOMBO_5),
        ("Bombo 6", BOMBO_6),
    ]

    puntos_equipos_globales, puntos_goleadores_globales = calcular_puntuaciones_globales()

    conteo_selecciones = {}

    apuestas = Apuesta.objects.all()

    for apuesta in apuestas:
        for i in range(1, 13):
            equipo = getattr(apuesta, f"equipo_{i}")
            conteo_selecciones[equipo] = conteo_selecciones.get(equipo, 0) + 1

    bombos_puntuaciones = []

    for nombre_bombo, equipos_bombo in bombos:
        equipos_ordenados = sorted(equipos_bombo, key=lambda equipo: equipo[1])

        equipos_del_bombo = []

        for nombre_equipo, _ in equipos_ordenados:
            info = obtener_info_equipo(nombre_equipo)
            puntos = calcular_puntos_equipo_por_fase(
                nombre_equipo,
                puntos_equipos_globales
            )

            equipos_del_bombo.append({
                "equipo": info,
                "puntos": puntos,
                "veces_elegida": conteo_selecciones.get(nombre_equipo, 0),
            })

        bombos_puntuaciones.append({
            "nombre": nombre_bombo,
            "equipos": equipos_del_bombo,
        })

    conteo_goleadores = {}

    for apuesta in apuestas:
        clave = (
            apuesta.goleador,
            apuesta.equipo_goleador,
        )

        conteo_goleadores[clave] = (
            conteo_goleadores.get(clave, 0) + 1
        )

    goleadores_elegidos = (
        Apuesta.objects
        .values("goleador", "equipo_goleador")
        .distinct()
        .order_by("equipo_goleador", "goleador")
    )

    goleadores = []

    for item in goleadores_elegidos:
        puntos = calcular_puntos_goleador_por_fase(
            item["goleador"],
            item["equipo_goleador"],
            puntos_goleadores_globales
        )

        equipo_info = obtener_info_equipo(item["equipo_goleador"])

        goleadores.append({
            "jugador": item["goleador"],
            "equipo": equipo_info,
            "puntos": puntos,
            "veces_elegido": conteo_goleadores.get(
                (
                    item["goleador"],
                    item["equipo_goleador"],
                ),
                0,
            ),
        })

    goleadores.sort(
        key=lambda x: x["jugador"].lower()
    )

    return render(
        request,
        "apuestas/puntuaciones.html",
        {
            "bombos_puntuaciones": bombos_puntuaciones,
            "goleadores": goleadores,
        }
    )

def obtener_resumen_ideal_cuchara():
    bombos = [BOMBO_1, BOMBO_2, BOMBO_3, BOMBO_4, BOMBO_5, BOMBO_6]

    puntos_equipos_globales, puntos_goleadores_globales = calcular_puntuaciones_globales()

    goleadores_elegidos = (
        Apuesta.objects
        .values("goleador", "equipo_goleador")
        .distinct()
    )

    goleadores = []

    for item in goleadores_elegidos:
        puntos_goleador = calcular_puntos_goleador_por_fase(
            item["goleador"],
            item["equipo_goleador"],
            puntos_goleadores_globales
        )["TOTAL"]

        goleadores.append({
            "jugador": item["goleador"],
            "equipo": item["equipo_goleador"],
            "equipo_info": obtener_info_equipo(item["equipo_goleador"]),
            "puntos": puntos_goleador,
        })

    filas = []

    for tipo in ["APUESTA IDEAL", "CUCHARA DE MADERA"]:
        equipos_finales = []
        puntos_total = 0

        for bombo in bombos:
            equipos_bombo = []

            for nombre_equipo, _ in bombo:
                puntos = calcular_puntos_equipo_por_fase(
                    nombre_equipo,
                    puntos_equipos_globales
                )["TOTAL"]
                info = obtener_info_equipo(nombre_equipo)

                equipos_bombo.append({
                    "nombre": nombre_equipo,
                    "info": info,
                    "puntos": puntos,
                })

            if tipo == "APUESTA IDEAL":
                seleccionados = sorted(
                    equipos_bombo,
                    key=lambda x: (-x["puntos"], x["nombre"])
                )[:2]

                goleador = sorted(
                    goleadores,
                    key=lambda x: (-x["puntos"], x["jugador"])
                )[0] if goleadores else None

            else:
                seleccionados = sorted(
                    equipos_bombo,
                    key=lambda x: (x["puntos"], x["nombre"])
                )[:2]

                goleador = sorted(
                    goleadores,
                    key=lambda x: (x["puntos"], x["jugador"])
                )[0] if goleadores else None

            seleccionados = sorted(seleccionados, key=lambda x: x["nombre"])

            equipos_finales.extend(seleccionados)
            puntos_total += sum(equipo["puntos"] for equipo in seleccionados)

            if goleador:
                puntos_total += goleador["puntos"]

        filas.append({
            "tipo": tipo,
            "equipos": equipos_finales,
            "goleador": goleador,
            "puntos": puntos_total,
        })

    return filas

