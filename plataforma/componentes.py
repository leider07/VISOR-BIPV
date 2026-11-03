"""Piezas de interfaz reutilizables: encabezado, pie, filtros y selector de fechas."""
from datetime import date, timedelta

import pandas as pd
from dash import dcc, html

from . import datos as D
from .graficas import color_modulo, etiqueta_superficie

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
MESES_LARGO = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
               "Septiembre", "Octubre", "Noviembre", "Diciembre"]

AMBIENTALES = {"irradiancia", "temperatura_ambiente", "temperatura_modulo", "humedad_relativa", "velocidad_viento"}


def paginas():
    """Pestañas disponibles según la instalación: (ruta, nombre)."""
    p = []
    if D.es_resumen_fijo():
        p.append(("/", "Resumen"))
    if D.variables() & AMBIENTALES:
        p.append(("/clima", "Clima"))
    p += [("/energia", "Energía"), ("/desempeno", "Desempeño"), ("/explorar", "Explorar"), ("/datos", "Tus datos")]
    return p


def palabras():
    """Sustantivos de la interfaz según la base: módulo/vidrio y superficie/cara."""
    m = D.metadatos()
    n, s = m.get("modulo_palabra", "módulo"), m.get("superficie_palabra", "superficie")
    return {"n": n, "np": n + "s", "s": s, "sp": s + "s"}


# ---------------------------------------------------------------- fechas
def f_corta(iso):
    d = date.fromisoformat(iso)
    return f"{d.day:02d} {MESES[d.month - 1]} {d.year}"


def rango_texto(ini, fin):
    return f"{f_corta(ini)} – {f_corta(fin)}" if ini != fin else f_corta(ini)


def rangos_rapidos(meta):
    ini, fin = date.fromisoformat(meta["fecha_inicio"]), date.fromisoformat(meta["fecha_fin"])

    def atras(dias):
        return max(ini, fin - timedelta(days=dias - 1)).isoformat()

    def meses_atras(n):
        return max(ini, (pd.Timestamp(fin) - pd.DateOffset(months=n) + pd.Timedelta(days=1)).date()).isoformat()

    r = [("Todo el proyecto", ini.isoformat(), fin.isoformat()),
         ("Último día con datos", fin.isoformat(), fin.isoformat()),
         ("Últimos 7 días", atras(7), fin.isoformat()),
         ("Último mes", meses_atras(1), fin.isoformat()),
         ("Últimos 3 meses", meses_atras(3), fin.isoformat()),
         ("Últimos 6 meses", meses_atras(6), fin.isoformat())]
    for an in range(ini.year, fin.year + 1):
        r.append((f"Año {an}", max(ini, date(an, 1, 1)).isoformat(), min(fin, date(an, 12, 31)).isoformat()))
    return r


def meses_disponibles(meta):
    ini, fin = pd.Timestamp(meta["fecha_inicio"]), pd.Timestamp(meta["fecha_fin"])
    out = []
    for p in pd.period_range(ini, fin, freq="M"):
        a = max(ini, p.start_time).date().isoformat()
        b = min(fin, p.end_time).date().isoformat()
        out.append((f"{MESES_LARGO[p.month - 1]} {p.year}", a, b, p.strftime("%Y-%m")))
    return out


def icono_calendario(tam=18):
    return html.Img(src="/assets/img/iconos/calendario.svg", alt="", width=tam, height=tam, className="icono")


def selector_fechas(meta):
    rr = rangos_rapidos(meta)
    meses = meses_disponibles(meta)
    return html.Div(className="selector-fechas", children=[
        html.Span("Fechas", className="filtro-titulo"),
        html.Button(id="btn-fechas", className="btn-fechas", n_clicks=0, **{"aria-haspopup": "dialog"}, children=[
            icono_calendario(),
            html.Span(className="btn-fechas-texto", children=[
                html.Span(id="fechas-rango", className="btn-fechas-rango"),
                html.Span(id="fechas-texto")]),
            html.Img(src="/assets/img/iconos/flecha.svg", alt="", width=14, height=14, className="icono"),
        ]),
        html.Div(id="pop-fechas", className="pop-fechas", style={"display": "none"},
                 role="dialog", **{"aria-label": "Elegir rango de fechas"}, children=[
            html.Div(className="pop-col pop-rapidos", children=[
                html.Div("Rangos rápidos", className="pop-cabecera"),
                html.Div(className="pop-lista", children=[
                    html.Button(lbl, id={"type": "preset", "index": i}, n_clicks=0, className="preset")
                    for i, (lbl, _, _) in enumerate(rr)]),
            ]),
            html.Div(className="pop-col pop-personal", children=[
                html.Div("Personalizado", className="pop-cabecera"),
                dcc.Tabs(id="tabs-fechas", value="rango", className="tabs-fechas", children=[
                    dcc.Tab(label="Rango de fechas", value="rango", className="tab", selected_className="tab-activa",
                            children=html.Div(className="pop-rango", children=[
                                html.Label("Fecha inicial", htmlFor="fecha-ini"),
                                dcc.Input(id="fecha-ini", type="date", min=meta["fecha_inicio"],
                                          max=meta["fecha_fin"], className="input-fecha", debounce=True),
                                html.Label("Fecha final", htmlFor="fecha-fin"),
                                dcc.Input(id="fecha-fin", type="date", min=meta["fecha_inicio"],
                                          max=meta["fecha_fin"], className="input-fecha", debounce=True),
                                html.P(f"Hay datos del {f_corta(meta['fecha_inicio'])} al {f_corta(meta['fecha_fin'])}. "
                                       "Los rangos rápidos se cuentan hacia atrás desde el último día con datos.",
                                       className="pop-nota"),
                            ])),
                    dcc.Tab(label="Por mes", value="mes", className="tab", selected_className="tab-activa",
                            children=html.Div(className="pop-meses", children=[
                                html.Button(lbl, id={"type": "mes", "index": key}, n_clicks=0, className="mes")
                                for lbl, _, _, key in meses])),
                ]),
                html.Div(className="pop-acciones", children=[
                    html.Button("Cancelar", id="btn-cancelar", n_clicks=0, className="btn btn-sec"),
                    html.Button("Aplicar", id="btn-aplicar", n_clicks=0, className="btn btn-pri"),
                ]),
            ]),
        ]),
    ])


# ---------------------------------------------------------------- filtros
def opciones_modulos(superficie):
    return [{"label": html.Span([html.Span(className="punto", style={"background": color_modulo(r.color)}),
                                 r.etiqueta]), "value": r.modulo_id}
            for r in D.modulos_de(superficie).itertuples()]


def filtro_modulos(superficie, valor=None):
    valor = list(D.modulos_de(superficie).modulo_id) if valor is None else valor
    return dcc.Checklist(id="filtro-vidrios", options=opciones_modulos(superficie), value=valor, inline=True,
                         className="chips", inputClassName="chip-input", labelClassName="chip chip-claro")


def titulo_modulos():
    pal = palabras()
    m = D.modulos()
    if pal["n"] == "vidrio" and m.transmitancia_pct.notna().all():
        return "Vidrio (% de transmitancia)"
    return pal["np"].capitalize()


def barra_filtros(meta):
    sup = D.superficies()
    primera = sup.superficie_id.iloc[0]
    opciones_sup = [{"label": etiqueta_superficie(r, corta=True), "value": r.superficie_id} for r in sup.itertuples()]
    return html.Div(id="barra-filtros", className="barra-filtros", children=[
        selector_fechas(meta),
        html.Div(id="grupo-cara", className="grupo-filtro", children=[
            html.Span(f"{palabras()['s'].capitalize()} (elige una)", className="filtro-titulo"),
            dcc.RadioItems(id="filtro-cara", options=opciones_sup, value=primera, inline=True,
                           className="chips", inputClassName="chip-input", labelClassName="chip"),
        ]),
        html.Div(id="grupo-modulos", className="grupo-filtro", children=[
            html.Span(titulo_modulos(), className="filtro-titulo"),
            html.Div(id="caja-modulos", children=filtro_modulos(primera)),
        ]),
        html.Div(id="nota-filtros", className="nota-filtros"),
    ])


# ---------------------------------------------------------------- marco
def textos_marca(meta):
    """(franja superior, título de la marca, subtítulo de la marca)."""
    if D.es_resumen_fijo():
        return "Plataforma de monitoreo BIPV · Prototipo Sumicol", "Visor BIPV", "Sumicol · Medellín"
    lugar = " · ".join(x for x in [meta.get("ciudad"), meta.get("pais")] if x)
    return (f"Plataforma de monitoreo fotovoltaico · {meta['instalacion']}", "Visor fotovoltaico",
            " · ".join(x for x in [meta["instalacion"], meta.get("ciudad")] if x) or lugar)


def encabezado(meta):
    franja, marca, sub = textos_marca(meta)
    return html.Header(className="encabezado", children=[
        html.Div(className="franja", children=html.Div(className="contenedor franja-int", children=[
            html.Span(franja),
            html.Span(f"Datos históricos · {rango_texto(meta['fecha_inicio'], meta['fecha_fin'])}"),
        ])),
        html.Div(className="contenedor barra-nav", children=[
            dcc.Link(href="/", className="marca", children=[
                html.Img(src="/assets/img/logos/integra-logo.png",
                         alt="Integra – Plataforma de Integración Fotovoltaica en Edificaciones", className="logo"),
                html.Span(className="separador"),
                html.Span(className="marca-texto", children=[marca, html.Br(), html.Small(sub)]),
            ]),
            html.Nav(**{"aria-label": "Secciones"}, className="nav", children=[
                dcc.Link(nombre, href=ruta, id={"type": "nav", "index": ruta}, className="nav-link")
                for ruta, nombre in paginas()]),
        ]),
    ])


def aviso_base_propia(meta):
    """Franja que recuerda que se está viendo una base cargada por el visitante."""
    return html.Div(className="franja-base", children=html.Div(className="contenedor franja-base-int", children=[
        html.Span(["Estás viendo tu base ", html.B(f"«{meta['instalacion']}»"),
                   ". Solo tú la ves en esta pestaña del navegador."]),
        html.Button("Volver a la plataforma de Sumicol", id={"type": "volver", "index": "franja"}, n_clicks=0,
                    className="enlace-btn")]))


def pie():
    return html.Footer(className="pie", children=[
        html.Div(className="pie-logos", children=html.Div(className="contenedor", children=html.Img(
            src="/assets/img/logos/logos-aliados.png",
            alt="Entidades aliadas: SGR, Universidad de Antioquia, Corantioquia, Sumicol, SAI, Andercol, "
                "Gobernaciones de Antioquia, Caldas, Quindío y Risaralda", className="logos-aliados"))),
        html.Div(className="pie-franja", children=html.Div(className="contenedor pie-int", children=[
            html.Span(className="pie-marca", children=[
                html.Img(src="/assets/img/logos/favicon.png", alt="", className="pie-icono"),
                "Proyecto Integra · Plataforma de Integración Fotovoltaica en Edificaciones"]),
            html.A("proyecto-integra.site", href="https://proyecto-integra.site/", target="_blank", rel="noopener"),
        ])),
    ])


# ---------------------------------------------------------------- tarjetas
def tarjeta_grafica(titulo, subtitulo, figura, extra=None):
    from .graficas import CONFIG
    hijos = [html.Div(className="tarjeta-cab", children=[html.H3(titulo), html.P(subtitulo)])]
    hijos.append(dcc.Graph(figure=figura, config=CONFIG, className="grafica"))
    if extra is not None:
        hijos.append(extra)
    return html.Section(className="tarjeta tarjeta-grafica", children=hijos)


def kpi(etiqueta, valor, unidad, color):
    return html.Div(className="tarjeta kpi", children=[
        html.Div(etiqueta, className="kpi-etq"),
        html.Div(className="kpi-val", children=[valor, html.Span(f" {unidad}", className="kpi-uni")]),
        html.Div(className="kpi-barra", style={"background": color}),
    ])


def aviso(texto):
    return html.Div(texto, className="tarjeta aviso")
