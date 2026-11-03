"""Pestaña Resumen del prototipo BIPV Sumicol (contenido fijo: textos, fotos y equipos)."""
from datetime import date

from dash import html

from . import datos as D
from .componentes import f_corta

IMG = "/assets/img/sumicol"


def cronograma_ancho():
    """Cronograma en columnas: desde, hasta, inclinada, vertical."""
    cr = D.cronograma()
    out = cr.pivot_table(index=["desde", "hasta"], columns="superficie_id", values="orientacion",
                         aggfunc="first").reset_index().sort_values("desde")
    return out


def resumen():
    meta = D.metadatos()
    ini, fin = date.fromisoformat(meta["fecha_inicio"]), date.fromisoformat(meta["fecha_fin"])
    meses = max(1, round((fin - ini).days / 30.44))
    crono = cronograma_ancho()
    caras = [
        ("0°", "Cara superior", "Siempre orientada hacia el cenit (mira al cielo)"),
        ("60°", "Cara inclinada", "Se giró entre Norte, Sur, Este y Oeste"),
        ("90°", "Cara vertical", "Se giró entre Norte, Sur, Este y Oeste"),
    ]
    pasos = [
        ("1", "Elige los filtros", "Un rango de fechas (o un rango rápido), una cara y los vidrios que quieres "
                                   "comparar. Aplican a todas las pestañas.", "captura-filtros.png"),
        ("2", "Mira el clima", "Radiación solar, horas de sol, temperatura ambiente y de los vidrios, y viento.",
         "captura-clima.png"),
        ("3", "Compara la energía", "Cuánta energía generó cada vidrio por día, en total y en promedio.",
         "captura-energia.png"),
        ("4", "Revisa el desempeño", "Potencia y eficiencia de cada vidrio a lo largo del día.",
         "captura-desempeno.png"),
    ]
    return html.Div([
        html.Section(className="hero", children=html.Div(className="contenedor hero-int", children=[
            html.Div(className="hero-texto", children=[
                html.Div("Prototipo BIPV · Sumicol, Medellín", className="ceja"),
                html.H1("Vidrios fotovoltaicos que generan energía en la fachada"),
                html.P("Esta plataforma muestra los datos históricos del prototipo de integración fotovoltaica en "
                       "edificaciones (BIPV) instalado en Sumicol: 12 módulos de vidrio semitransparente con cuatro "
                       "niveles de transmitancia, montados en tres caras con inclinaciones de 0°, 60° y 90°.",
                       className="parrafo"),
                html.Div(className="hero-botones", children=[
                    html.A("Explorar los datos", href="/clima", className="btn btn-pri"),
                    html.A("¿Cómo funciona?", href="#como", className="btn btn-sec"),
                ]),
            ]),
            html.Div(className="hero-foto", children=[
                html.Img(src=f"{IMG}/montaje-1.jpg", alt="Prototipo BIPV en la terraza de Sumicol"),
                html.Div(className="hero-sello", children=[f"{f_corta(meta['fecha_inicio'])} – {f_corta(meta['fecha_fin'])}",
                                                         html.Br(), html.Span("datos históricos")]),
            ]),
        ])),
        html.Div(className="contenedor", children=[
            html.Div(className="rejilla-4 bloque", children=[
                html.Div(className="tarjeta cifra", children=[html.Div(v, className="cifra-v"), html.Div(t)])
                for v, t in [("12", "módulos BIPV de 0,72 m²"), ("3", "caras: 0°, 60° y 90°"),
                             ("4", "vidrios: 10, 30, 40 y 80 % de transmitancia"),
                             (str(meses), "meses de medición, minuto a minuto")]]),
            html.Section(className="bloque-grande dos-col", children=[
                html.Div(className="col-texto", children=[
                    html.Div("El montaje", className="ceja"),
                    html.H2("Tres caras, cuatro vidrios"),
                    html.P("En cada cara se midió, minuto a minuto, la electricidad que produce cada vidrio y la "
                           "radiación solar que recibe. La cara superior mira siempre al cielo; la inclinada y la "
                           "vertical se fueron girando para mirar al Norte, Sur, Este y Oeste.", className="parrafo"),
                    html.Div(className="lista-caras", children=[
                        html.Div(className="cara-item", children=[
                            html.Div(a, className="cara-ang"),
                            html.Div([html.Div(n, className="cara-nom"), html.Div(d, className="cara-det")])])
                        for a, n, d in caras]),
                ]),
                html.Img(src=f"{IMG}/montaje-2.jpg", alt="Vista del prototipo con las caras inclinada y vertical",
                         className="foto-grande"),
            ]),
            html.Div(className="rejilla-3 galeria", children=[
                html.Img(src=f"{IMG}/montaje-3.jpg", alt="Detalle de los vidrios semitransparentes"),
                html.Img(src=f"{IMG}/montaje-4.jpg", alt="Otra vista del prototipo"),
                html.Img(src=f"{IMG}/montaje-1.jpg", alt="Prototipo con la ciudad de fondo"),
            ]),
            html.Section(className="bloque-grande", children=[
                html.Div("Instrumentación", className="ceja"),
                html.H2("Equipos de medición"),
                html.Div(className="tarjeta equipo-principal", children=[
                    html.Img(src=f"{IMG}/trazador-iv.jpg", alt="Trazador de curvas I-V instalado en su caja",
                             className="equipo-foto-grande"),
                    html.Div(className="equipo-texto", children=[
                        html.Span("Desarrollo propio del grupo", className="etiqueta-sol"),
                        html.H3("Trazador de curvas I-V"),
                        html.P("Equipo diseñado por el grupo de investigación que, mediante la técnica de carga "
                               "electrónica, recorre la curva corriente–voltaje de cada vidrio fotovoltaico. De cada "
                               "curva se obtiene la potencia máxima, el voltaje y la corriente del vidrio en ese "
                               "momento. Hay un trazador por cara, que mide sus cuatro vidrios minuto a minuto.",
                               className="parrafo"),
                    ]),
                ]),
                html.Div(className="rejilla-4", children=[
                    html.Div(className="tarjeta equipo", children=[
                        html.Img(src=f"{IMG}/{img}", alt=nombre, className="equipo-foto"),
                        html.Div(qué, className="equipo-mide"),
                        html.Div(nombre, className="equipo-nombre"),
                        html.P(desc)])
                    for img, qué, nombre, desc in [
                        ("sensor-radiacion.png", "Radiación solar", "Piranómetro RK200-04",
                         "Mide la radiación solar que llega a cada cara. Hay uno en el mismo plano de cada cara."),
                        ("sensor-termistor.png", "Temperatura de los vidrios", "Termistor NTC B3950 10K de película delgada",
                         "Sensor delgado adherido a los vidrios para medir su temperatura."),
                        ("sensor-ambiente.png", "Temperatura ambiente", "Sensor SHT31",
                         "Mide la temperatura y la humedad del aire alrededor del prototipo."),
                        ("sensor-viento.png", "Viento", "Sensor JXCT-3001-FSFX",
                         "Estación de viento que mide la velocidad del aire sobre el prototipo."),
                    ]]),
            ]),
            html.Section(className="bloque-grande", children=[
                html.Div("Metodología", className="ceja"),
                html.H2("Cómo se procesaron los datos"),
                html.Div(className="rejilla-3", children=[
                    html.Div(className="tarjeta metodo", children=[html.H3(t), html.P(d)]) for t, d in [
                        ("Horario analizado",
                         "Se tienen en cuenta solo las mediciones tomadas entre las 5:00 y las 19:00, cuando hay luz solar."),
                        ("Datos confiables",
                         "Se eliminaron las mediciones que no eran confiables: lecturas fuera de rango, fallas "
                         "momentáneas de los equipos o sombras parciales. Los días con muy pocas mediciones válidas no "
                         "se cuentan en la energía."),
                        ("Promedios",
                         "Las gráficas «a lo largo del día» muestran el promedio de cada hora entre todos los días del "
                         "rango elegido, incluyendo días soleados y nublados."),
                    ]]),
            ]),
            html.Section(id="como", className="bloque-grande", children=[
                html.Div("Guía rápida", className="ceja"),
                html.H2("Cómo usar la plataforma"),
                html.Div(className="rejilla-4", children=[
                    html.Div(className="tarjeta paso", children=[
                        html.Img(src=f"{IMG}/{img}", alt=f"Captura: {t}", className="paso-img"),
                        html.Div(className="paso-tit", children=[html.Span(n, className="paso-num"), t]),
                        html.P(d)]) for n, t, d, img in pasos]),
            ]),
            html.Section(className="bloque-grande dos-col cronograma", children=[
                html.Div(className="col-texto", children=[
                    html.Div("Referencia", className="ceja"),
                    html.H2("Cronograma de orientaciones"),
                    html.P("La cara inclinada y la vertical se giraron periódicamente. Esta tabla indica hacia dónde "
                           "miraba cada una en cada periodo, para interpretar los datos de una fecha concreta.",
                           className="parrafo"),
                ]),
                html.Div(className="tarjeta tabla-caja", children=html.Table(className="tabla", children=[
                    html.Thead(html.Tr([html.Th("Desde"), html.Th("Hasta"),
                                        html.Th("Cara inclinada (60°) mira al"), html.Th("Cara vertical (90°) mira al")])),
                    html.Tbody([html.Tr([html.Td(f_corta(r.desde)), html.Td(f_corta(r.hasta)),
                                         html.Td(r.inclinada, className="fuerte"), html.Td(r.vertical, className="fuerte")])
                                for r in crono.itertuples()]),
                ])),
            ]),
        ]),
    ])


