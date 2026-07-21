from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.db.models import Prefetch
from django.core.cache import cache


from .models import Partido, Apuesta, GoleadorPartido, GoleadorTorneo
from .forms import ApuestaForm, PartidoForm
from .choices import (
    TODOS_EQUIPOS,
    EQUIPOS_INFO,
    BOMBO_1,
    BOMBO_2,
    BOMBO_3,
    BOMBO_4,
    BOMBO_5,
    BOMBO_6,
)

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer

import unicodedata
import json

CLAVE_CACHE_CLASIFICACION = "clasificacion_completa_v1"
TIEMPO_CACHE_CLASIFICACION = 3600


def inicio(request):
    return render(request, "apuestas/inicio.html")


def clave_orden_nombre(nombre):
    return (
        unicodedata.normalize("NFKD", nombre or "")
        .encode("ASCII", "ignore")
        .decode("ASCII")
        .lower()
    )


def obtener_info_equipo(nombre, equipos_eliminados=None):
    equipos_eliminados = equipos_eliminados or set()
    info = EQUIPOS_INFO.get(nombre, {})

    return {
        "nombre": nombre,
        "codigo": info.get("codigo", nombre[:3].upper()),
        "flag": info.get("flag", ""),
        "eliminado": nombre in equipos_eliminados,
    }


@staff_member_required
def nueva_apuesta(request):
    if request.method == "POST":
        form = ApuestaForm(request.POST)
        if form.is_valid():
            form.save()
            sincronizar_goleadores_partidos()
            return redirect("ver_apuestas")
    else:
        form = ApuestaForm()

    return render(request, "apuestas/formulario_apuesta.html", {"form": form})


@staff_member_required
def ver_apuestas(request):
    equipos_eliminados = obtener_equipos_eliminados()

    apuestas = sorted(
        Apuesta.objects.all(),
        key=lambda a: clave_orden_nombre(a.nombre),
    )

    leyenda = [
        obtener_info_equipo(nombre, equipos_eliminados)
        for nombre, _ in TODOS_EQUIPOS
    ]

    apuestas_preparadas = []

    for apuesta in apuestas:
        equipos = [
            obtener_info_equipo(getattr(apuesta, f"equipo_{i}"), equipos_eliminados)
            for i in range(1, 13)
        ]


        apuestas_preparadas.append({
            "apuesta": apuesta,
            "equipos": equipos,
            "equipo_goleador_info": obtener_info_equipo(
                apuesta.equipo_goleador,
                equipos_eliminados,
            ),
        })

    return render(
        request,
        "apuestas/ver_apuestas.html",
        {
            "leyenda": leyenda,
            "apuestas_preparadas": apuestas_preparadas,
        },
    )


@staff_member_required
def editar_apuesta(request, apuesta_id):
    apuesta = get_object_or_404(Apuesta, id=apuesta_id)

    if request.method == "POST":
        form = ApuestaForm(request.POST, instance=apuesta)
        if form.is_valid():
            form.save()
            sincronizar_goleadores_partidos()
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
            "equipo",
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

    jornadas = []

    for codigo_fase, nombre_fase in Partido.FASES:
        partidos_fase = (
            Partido.objects
            .filter(fase=codigo_fase)
            .prefetch_related(
                Prefetch(
                    "goleadores",
                    queryset=GoleadorPartido.objects.order_by("jugador"),
                    to_attr="goleadores_prefetch",
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

        total_esperado = PARTIDOS_ESPERADOS_RESULTADOS.get(
            codigo_fase,
            len(partidos_preparados)
        )

        slots = []

        for index in range(total_esperado):
            if index < len(partidos_preparados):
                slots.append({
                    "vacio": False,
                    "item": partidos_preparados[index],
                    "numero": index + 1,
                })
            else:
                slots.append({
                    "vacio": True,
                    "item": None,
                    "numero": index + 1,
                })

        jornadas.append({
            "codigo": codigo_fase,
            "nombre": nombre_fase,
            "partidos": slots,
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
        },
    )


def clasificacion(request):
    contexto = obtener_contexto_clasificacion()

    return render(
        request,
        "apuestas/clasificacion.html",
        contexto,
    )


def asignar_posiciones(clasificacion_data):
    posicion = 0
    posicion_real = 0
    puntos_anteriores = None

    for item in clasificacion_data:
        posicion += 1

        if puntos_anteriores != item["puntos_totales"]:
            posicion_real = posicion

        item["posicion"] = posicion_real
        puntos_anteriores = item["puntos_totales"]


def cuentaatras(request):
    contexto_clasificacion = obtener_contexto_clasificacion()

    clasificacion_completa = contexto_clasificacion.get(
        "clasificacion",
        [],
    )

    primero = (
        clasificacion_completa[0]
        if len(clasificacion_completa) >= 1
        else None
    )

    segundo = (
        clasificacion_completa[1]
        if len(clasificacion_completa) >= 2
        else None
    )

    tercero = (
        clasificacion_completa[2]
        if len(clasificacion_completa) >= 3
        else None
    )

    ultimo = (
        clasificacion_completa[-1]
        if clasificacion_completa
        else None
    )

    contexto = {
        "primero": primero,
        "segundo": segundo,
        "tercero": tercero,
        "ultimo": ultimo,
        "fecha_inicio_torneo": "2028-06-09T21:00:00+02:00",
    }

    return render(
        request,
        "apuestas/cuentaatras.html",
        contexto,
    )


def obtener_contexto_clasificacion():
    datos_cache = cache.get(CLAVE_CACHE_CLASIFICACION)

    if datos_cache is not None:
        return datos_cache

    equipos_eliminados = obtener_equipos_eliminados()
    fase_actual = obtener_fase_actual_partidos()

    info_equipos_base = {
        nombre_equipo: obtener_info_equipo(
            nombre_equipo,
            equipos_eliminados,
        )
        for nombre_equipo, _ in TODOS_EQUIPOS
    }

    puntos_equipos_globales, puntos_goleadores_globales = (
        calcular_puntuaciones_globales()
    )

    apuestas = list(
        Apuesta.objects.all().order_by("nombre")
    )

    clasificacion_data = []

    equipos_que_ya_jugaron_fase_actual = set()

    if fase_actual:
        partidos_jugados_fase_actual = Partido.objects.filter(
            fase=fase_actual,
            jugado=True,
        ).only(
            "equipo_local",
            "equipo_visitante",
        )

        for partido in partidos_jugados_fase_actual:
            equipos_que_ya_jugaron_fase_actual.add(
                partido.equipo_local
            )
            equipos_que_ya_jugaron_fase_actual.add(
                partido.equipo_visitante
            )

    for apuesta in apuestas:
        (
            puntos_equipos,
            puntos_goleador,
            puntos_totales_orden,
            detalle_equipos,
        ) = calcular_puntos_apuesta(
            apuesta,
            puntos_equipos_globales,
            puntos_goleadores_globales,
        )

        equipos_apuesta = []

        nombres_equipos = [
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

        equipos_jugados = 0
        equipos_pendientes = 0
        pendientes_detalle = []

        for nombre_equipo in nombres_equipos:
            info = info_equipos_base[nombre_equipo].copy()

            pendiente_fase_actual = bool(
                fase_actual
                and nombre_equipo not in equipos_que_ya_jugaron_fase_actual
                and nombre_equipo not in equipos_eliminados
            )

            info["pendiente_fase_actual"] = pendiente_fase_actual

            if pendiente_fase_actual:
                equipos_pendientes += 1
                pendientes_detalle.append(info["codigo"])
            else:
                equipos_jugados += 1

            equipos_apuesta.append(info)

        equipo_goleador_info = info_equipos_base[
            apuesta.equipo_goleador
        ].copy()

        goleador_pendiente = bool(
            fase_actual
            and apuesta.equipo_goleador
            not in equipos_que_ya_jugaron_fase_actual
            and apuesta.equipo_goleador not in equipos_eliminados
        )

        equipo_goleador_info[
            "pendiente_fase_actual"
        ] = goleador_pendiente

        if goleador_pendiente:
            pendientes_detalle.append(
                equipo_goleador_info["codigo"]
            )

        clasificacion_data.append({
            "apuesta": apuesta,
            "equipos": equipos_apuesta,
            "equipo_goleador_info": equipo_goleador_info,

            "puntos": puntos_equipos + puntos_goleador,
            "puntos_equipos": puntos_equipos,
            "puntos_goleador": puntos_goleador,

            "puntos_display": (
                f"{puntos_equipos + puntos_goleador}"
                f".{puntos_goleador:02d}"
            ),

            "puntos_totales": puntos_totales_orden,

            "detalle_equipos": detalle_equipos,
            "equipos_jugados": equipos_jugados,
            "equipos_pendientes": equipos_pendientes,
            "pendientes_detalle": pendientes_detalle,
        })

    clasificacion_data.sort(
        key=lambda item: (
            -item["puntos_totales"],
            clave_orden_nombre(item["apuesta"].nombre),
        )
    )

    asignar_posiciones(clasificacion_data)

    for item in clasificacion_data:
        detalle_modal = {
            "posicion": item.get("posicion", ""),
            "nombre": item["apuesta"].nombre,
            "puntos": item.get("puntos_display", "0"),
            "equipos_jugados": item.get(
                "equipos_jugados",
                0,
            ),
            "equipos_pendientes": item.get(
                "equipos_pendientes",
                0,
            ),
            "pendientes_detalle": item.get(
                "pendientes_detalle",
                [],
            ),
            "equipos": [
                {
                    "nombre": equipo.get("nombre", ""),
                    "codigo": equipo.get("codigo", ""),
                    "flag": equipo.get("flag", ""),
                    "eliminado": bool(
                        equipo.get("eliminado", False)
                    ),
                    "pendiente": bool(
                        equipo.get(
                            "pendiente_fase_actual",
                            False,
                        )
                    ),
                }
                for equipo in item.get("equipos", [])
            ],
            "goleador": {
                "nombre": item["apuesta"].goleador,
                "equipo": item[
                    "equipo_goleador_info"
                ].get(
                    "nombre",
                    item["apuesta"].equipo_goleador,
                ),
                "flag": item[
                    "equipo_goleador_info"
                ].get("flag", ""),
                "eliminado": bool(
                    item[
                        "equipo_goleador_info"
                    ].get("eliminado", False)
                ),
                "pendiente": bool(
                    item[
                        "equipo_goleador_info"
                    ].get(
                        "pendiente_fase_actual",
                        False,
                    )
                ),
            },
        }

        item["modal_json"] = json.dumps(
            detalle_modal,
            ensure_ascii=False,
        )

    contexto = {
        "clasificacion": clasificacion_data,
        "resumen_ideal_cuchara": (
            obtener_resumen_ideal_cuchara()
        ),
    }

    cache.set(
        CLAVE_CACHE_CLASIFICACION,
        contexto,
        TIEMPO_CACHE_CLASIFICACION,
    )

    return contexto


def obtener_datos_clasificacion():
    equipos_eliminados = obtener_equipos_eliminados()
    apuestas = list(
        Apuesta.objects.all().order_by("nombre")
    )

    puntos_equipos_globales, puntos_goleadores_globales = calcular_puntuaciones_globales()

    clasificacion_data = []

    for apuesta in apuestas:
        puntos_equipos, puntos_goleador, puntos_totales, _ = calcular_puntos_apuesta(
            apuesta,
            puntos_equipos_globales,
            puntos_goleadores_globales,
        )

        equipos = [
            obtener_info_equipo(
                getattr(apuesta, f"equipo_{i}"),
                equipos_eliminados,
            )
            for i in range(1, 13)
        ]

        clasificacion_data.append({
            "apuesta": apuesta,
            "equipos": equipos,
            "equipo_goleador_info": obtener_info_equipo(
                apuesta.equipo_goleador,
                equipos_eliminados,
            ),
            "puntos_totales": puntos_totales,
            "puntos_display": (
                f"{puntos_equipos + puntos_goleador}"
                f".{puntos_goleador:02d}"
            ),
        })

    clasificacion_data.sort(
        key=lambda x: (
            -x["puntos_totales"],
            clave_orden_nombre(x["apuesta"].nombre),
        )
    )

    asignar_posiciones(clasificacion_data)

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
            (partido.equipo_local, partido.goles_local, partido.goles_visitante),
            (partido.equipo_visitante, partido.goles_visitante, partido.goles_local),
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
            clave_goleador = (goleador.jugador, goleador.equipo)

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


def calcular_puntos_apuesta(
    apuesta,
    puntos_equipos_globales=None,
    puntos_goleadores_globales=None,
):
    if puntos_equipos_globales is None or puntos_goleadores_globales is None:
        puntos_equipos_globales, puntos_goleadores_globales = calcular_puntuaciones_globales()

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
    detalle_equipos = {}

    for equipo in equipos_apostados:
        puntos_equipo = puntos_equipos_globales.get(
            equipo,
            crear_diccionario_fases(),
        )

        total_equipo = puntos_equipo.get("TOTAL", 0)
        puntos_equipos += total_equipo

        detalle_equipos[equipo] = {
            "total": total_equipo,
            "fases": {
                fase: datos["valor"]
                for fase, datos in puntos_equipo.items()
                if fase != "TOTAL" and datos["valor"] > 0
            },
        }

    puntos_goleador = puntos_goleadores_globales.get(
        (
            apuesta.goleador,
            apuesta.equipo_goleador,
        ),
        crear_diccionario_fases(),
    ).get("TOTAL", 0)

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
    resumen_ideal_cuchara = obtener_resumen_ideal_cuchara()
    fase_clasificacion = obtener_fase_clasificacion()

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="EuroMundial_Porra_Clasificacion_{fase_clasificacion}.pdf"'
    )

    doc = SimpleDocTemplate(
        response,
        pagesize=landscape(A4),
        rightMargin=8,
        leftMargin=8,
        topMargin=8,
        bottomMargin=8,
    )

    elementos = []

    def puntos_pdf(valor):
        return str(valor).replace(".", ",")

    resumen_datos = [[
        "",
        "PUNTOS",
        "EQUIPO 1", "EQUIPO 2", "EQUIPO 3", "EQUIPO 4",
        "EQUIPO 5", "EQUIPO 6", "EQUIPO 7", "EQUIPO 8",
        "EQUIPO 9", "EQUIPO 10", "EQUIPO 11", "EQUIPO 12",
        "GOLEADOR",
    ]]

    for fila in resumen_ideal_cuchara:
        resumen_datos.append([
            fila["tipo"],
            puntos_pdf(f"{fila['puntos']:.2f}"),
            *[equipo["nombre"] for equipo in fila["equipos"]],
            fila["goleador"]["jugador"] if fila.get("goleador") else "-",
        ])

    tabla_resumen = Table(
        resumen_datos,
        repeatRows=1,
        colWidths=[76, 38] + [45] * 12 + [80],
    )

    tabla_resumen.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.7, colors.black),
        ("BACKGROUND", (1, 0), (-1, 0), colors.HexColor("#f6b26b")),
        ("BACKGROUND", (1, 1), (1, -1), colors.yellow),
        ("BACKGROUND", (-1, 1), (-1, -1), colors.HexColor("#fce5cd")),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 5.2),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    elementos.append(tabla_resumen)
    elementos.append(Spacer(1, 8))

    cabecera = [
        fase_clasificacion,
        "PARTICIPANTE",
        "PUNTOS",
        "EQUIPO 1", "EQUIPO 2", "EQUIPO 3", "EQUIPO 4",
        "EQUIPO 5", "EQUIPO 6", "EQUIPO 7", "EQUIPO 8",
        "EQUIPO 9", "EQUIPO 10", "EQUIPO 11", "EQUIPO 12",
        "GOLEADOR",
    ]

    datos = [cabecera]

    for item in clasificacion_data:
        apuesta = item["apuesta"]

        datos.append([
            item["posicion"],
            apuesta.nombre,
            puntos_pdf(item["puntos_display"]),
            *[equipo["nombre"] for equipo in item["equipos"]],
            apuesta.goleador,
        ])

    tabla = Table(
        datos,
        repeatRows=1,
        colWidths=[22, 84, 38] + [45] * 12 + [82],
    )

    tabla.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.55, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f6b26b")),
        ("BACKGROUND", (2, 1), (2, -1), colors.yellow),
        ("BACKGROUND", (-1, 1), (-1, -1), colors.HexColor("#fce5cd")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 4.7),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (1, 1), (1, -1), "LEFT"),
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
        crear_diccionario_fases(),
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
    equipos_eliminados = obtener_equipos_eliminados()

    apuestas = list(
        Apuesta.objects.all().order_by("nombre")
    )

    conteo_selecciones = {}

    for apuesta in apuestas:
        for i in range(1, 13):
            equipo = getattr(apuesta, f"equipo_{i}")
            conteo_selecciones[equipo] = conteo_selecciones.get(equipo, 0) + 1

    bombos_puntuaciones = []

    for nombre_bombo, equipos_bombo in bombos:
        equipos_ordenados = sorted(equipos_bombo, key=lambda equipo: equipo[1])

        equipos_del_bombo = []

        for nombre_equipo, _ in equipos_ordenados:
            info = obtener_info_equipo(nombre_equipo, equipos_eliminados)

            puntos = calcular_puntos_equipo_por_fase(
                nombre_equipo,
                puntos_equipos_globales,
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

        conteo_goleadores[clave] = conteo_goleadores.get(clave, 0) + 1

    goleadores_elegidos = (
        Apuesta.objects
        .values("goleador", "equipo_goleador")
        .distinct()
    )

    goleadores = []

    for item in goleadores_elegidos:
        puntos = calcular_puntos_goleador_por_fase(
            item["goleador"],
            item["equipo_goleador"],
            puntos_goleadores_globales,
        )

        equipo_info = obtener_info_equipo(
            item["equipo_goleador"],
            equipos_eliminados,
        )

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
        key=lambda x: clave_orden_nombre(x["jugador"])
    )

    return render(
        request,
        "apuestas/puntuaciones.html",
        {
            "bombos_puntuaciones": bombos_puntuaciones,
            "goleadores": goleadores,
        },
    )

def obtener_resumen_ideal_cuchara():

    cache_key = "resumen_ideal_cuchara"

    resumen_cache = cache.get(cache_key)

    if resumen_cache is not None:
        return resumen_cache
    
    bombos = [BOMBO_1, BOMBO_2, BOMBO_3, BOMBO_4, BOMBO_5, BOMBO_6]

    equipos_eliminados = obtener_equipos_eliminados()
    fase_actual = obtener_fase_actual_partidos()

    equipos_que_ya_jugaron_fase_actual = set()

    if fase_actual:
        partidos_jugados_fase_actual = Partido.objects.filter(
            fase=fase_actual,
            jugado=True,
        )

        for partido in partidos_jugados_fase_actual:
            equipos_que_ya_jugaron_fase_actual.add(partido.equipo_local)
            equipos_que_ya_jugaron_fase_actual.add(partido.equipo_visitante)

    puntos_equipos_globales, puntos_goleadores_globales = calcular_puntuaciones_globales()

    goleadores_elegidos = (
        Apuesta.objects
        .values("goleador", "equipo_goleador")
        .distinct()
    )

    goleadores_apostados = []

    for item in goleadores_elegidos:
        puntos_goleador = calcular_puntos_goleador_por_fase(
            item["goleador"],
            item["equipo_goleador"],
            puntos_goleadores_globales,
        )["TOTAL"]

        equipo_info = obtener_info_equipo(
            item["equipo_goleador"],
            equipos_eliminados,
        )

        equipo_info["pendiente_fase_actual"] = (
            fase_actual
            and item["equipo_goleador"] not in equipos_que_ya_jugaron_fase_actual
            and item["equipo_goleador"] not in equipos_eliminados
        )

        goleadores_apostados.append({
            "jugador": item["goleador"],
            "equipo": item["equipo_goleador"],
            "equipo_info": equipo_info,
            "puntos": puntos_goleador,
            "manual": False,
        })

    goleadores_manuales = []

    for item in GoleadorTorneo.objects.filter(activo=True):
        equipo_info = obtener_info_equipo(
            item.equipo,
            equipos_eliminados,
        )

        equipo_info["pendiente_fase_actual"] = (
            fase_actual
            and item.equipo not in equipos_que_ya_jugaron_fase_actual
            and item.equipo not in equipos_eliminados
        )

        goleadores_manuales.append({
            "jugador": item.jugador,
            "equipo": item.equipo,
            "equipo_info": equipo_info,
            "puntos": item.puntos,
            "manual": True,
        })

    goleadores_ideal = goleadores_apostados + goleadores_manuales
    goleadores_cuchara = goleadores_apostados

    equipos_por_bombo = []

    for bombo in bombos:
        equipos_bombo = []

        for nombre_equipo, _ in bombo:
            puntos = calcular_puntos_equipo_por_fase(
                nombre_equipo,
                puntos_equipos_globales,
            )["TOTAL"]

            info = obtener_info_equipo(
                nombre_equipo,
                equipos_eliminados,
            )

            info["pendiente_fase_actual"] = (
                fase_actual
                and nombre_equipo not in equipos_que_ya_jugaron_fase_actual
                and nombre_equipo not in equipos_eliminados
            )

            equipos_bombo.append({
                "nombre": nombre_equipo,
                "info": info,
                "puntos": puntos,
            })

        equipos_por_bombo.append(equipos_bombo)

    def construir_fila(tipo):
        mejor = None

        if tipo == "APUESTA IDEAL":
            goleadores_base = goleadores_ideal
        else:
            goleadores_base = goleadores_cuchara

        for goleador in goleadores_base:
            equipos_finales = []
            puntos_equipos = 0

            for equipos_bombo in equipos_por_bombo:
                equipos_validos = [
                    equipo for equipo in equipos_bombo
                    if equipo["nombre"] != goleador["equipo"]
                ]

                if tipo == "APUESTA IDEAL":
                    seleccionados = sorted(
                        equipos_validos,
                        key=lambda x: (
                            -x["puntos"],
                            clave_orden_nombre(x["nombre"]),
                        )
                    )[:2]
                else:
                    seleccionados = sorted(
                        equipos_validos,
                        key=lambda x: (
                            x["puntos"],
                            clave_orden_nombre(x["nombre"]),
                        )
                    )[:2]

                seleccionados = sorted(
                    seleccionados,
                    key=lambda x: clave_orden_nombre(x["nombre"])
                )

                equipos_finales.extend(seleccionados)
                puntos_equipos += sum(equipo["puntos"] for equipo in seleccionados)

            puntos_total = puntos_equipos + goleador["puntos"]

            candidato = {
                "tipo": tipo,
                "equipos": equipos_finales,
                "goleador": goleador,
                "puntos": puntos_total,
                "puntos_goleador": goleador["puntos"],
                "puntos_display": (
                    f"{puntos_total}"
                    f".{goleador['puntos']:02d}"
                ),
                "puntos_totales_orden": puntos_total + (goleador["puntos"] / 100),
            }

            if mejor is None:
                mejor = candidato
                continue

            if tipo == "APUESTA IDEAL":
                if candidato["puntos_totales_orden"] > mejor["puntos_totales_orden"]:
                    mejor = candidato
            else:
                if candidato["puntos_totales_orden"] < mejor["puntos_totales_orden"]:
                    mejor = candidato

        return mejor

    resultado = [
        construir_fila("APUESTA IDEAL"),
        construir_fila("CUCHARA DE MADERA"),
    ]

    cache.set(cache_key, resultado, 3600)

    return resultado

PARTIDOS_ESPERADOS_FASE = {
    "1/16": 16,
    "1/8": 8,
    "1/4": 4,
    "1/2": 2,
    "FINAL": 1,
}

PARTIDOS_ESPERADOS_RESULTADOS = {
    "J1": 24,
    "J2": 24,
    "J3": 24,
    "1/16": 16,
    "1/8": 8,
    "1/4": 4,
    "1/2": 2,
    "FINAL": 1,
}

FASES_ELIMINACION = ["1/16", "1/8", "1/4", "1/2", "FINAL"]


def obtener_equipos_eliminados():
    cache_key = "equipos_eliminados"

    equipos_eliminados_cache = cache.get(cache_key)

    if equipos_eliminados_cache is not None:
        return set(equipos_eliminados_cache)

    equipos_vivos = set(nombre for nombre, _ in TODOS_EQUIPOS)
    equipos_eliminados = set()

    for fase in FASES_ELIMINACION:
        partidos_fase = list(
            Partido.objects
            .filter(fase=fase)
            .only(
                "equipo_local",
                "equipo_visitante",
                "jugado",
                "goles_local",
                "goles_visitante",
            )
        )

        if len(partidos_fase) < PARTIDOS_ESPERADOS_FASE[fase]:
            break

        equipos_fase = set()

        for partido in partidos_fase:
            equipos_fase.add(partido.equipo_local)
            equipos_fase.add(partido.equipo_visitante)

        equipos_eliminados.update(equipos_vivos - equipos_fase)
        equipos_vivos = equipos_fase

    partidos_eliminatorias = (
        Partido.objects
        .filter(
            fase__in=FASES_ELIMINACION,
            jugado=True,
        )
        .only(
            "equipo_local",
            "equipo_visitante",
            "goles_local",
            "goles_visitante",
        )
    )

    for partido in partidos_eliminatorias:
        if partido.goles_local > partido.goles_visitante:
            equipos_eliminados.add(partido.equipo_visitante)

        elif partido.goles_visitante > partido.goles_local:
            equipos_eliminados.add(partido.equipo_local)

    cache.set(cache_key, list(equipos_eliminados), 3600)

    return equipos_eliminados

def obtener_fase_actual_partidos():
    for codigo_fase, _ in Partido.FASES:
        partidos_fase = Partido.objects.filter(fase=codigo_fase)

        if partidos_fase.exists() and partidos_fase.filter(jugado=False).exists():
            return codigo_fase

    return None