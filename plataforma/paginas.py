"""Contenido de las pestañas Clima, Energía y Desempeño (se arman según lo que tenga la base)."""
from dash import dcc, html

from . import config as C
from . import datos as D
from . import graficas as G
from .componentes import aviso, f_corta, kpi, palabras, tarjeta_grafica


def titulos(ruta):
    p = palabras()
    v = D.variables()
    partes = []
    if "irradiancia" in v:
        partes.append(f"cuánto sol recibió cada {p['s']}")
    temp = [x for x, k in [("el ambiente", "temperatura_ambiente"), (f"los {p['np']}", "temperatura_modulo")] if k in v]
    if temp:
        partes.append("qué tan calientes estuvieron " + " y ".join(temp))
    if "humedad_relativa" in v:
        partes.append("cuánta humedad hubo")
    if "velocidad_viento" in v:
        partes.append("cuánto viento hubo")
    clima = (", ".join(partes[:-1]) + (", y " if len(partes) > 1 else "") + partes[-1]) if partes else ""
    t = {
        "/clima": ("Clima y recurso solar", (clima[:1].upper() + clima[1:] + ".") if clima else ""),
        "/energia": ("Energía generada", f"Energía de cada {p['n']} seleccionado en la {p['s']} elegida."),
        "/desempeno": ("Desempeño: potencia y eficiencia",
                       f"Cómo responde cada {p['n']} al sol a lo largo del día. La eficiencia es el porcentaje de "
                       f"la energía solar que llega al {p['n']} y se convierte en electricidad."),
    }
    return t[ruta]


def _num(x, dec=1):
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _nombre_superficie(sid):
    s = D.superficies()
    return s[s.superficie_id == sid].nombre.iloc[0]


# =================================================================== CLIMA
def clima(f):
    ini, fin = f["ini"], f["fin"]
    v = D.variables()
    p = palabras()
    irr = D.irr_hora(ini, fin) if "irradiancia" in v else None
    hsp = D.hsp_dia(ini, fin) if "irradiancia" in v else None
    met = D.meteo_hora(ini, fin)
    tec = D.tecnologias_de(f["modulos"])
    ids_t = list(D.modulos_por_tecnologia(tec, solo_con_temperatura=True).modulo_id)
    tv = D.temp_modulo_hora(ini, fin, ids_t)

    kp = []
    if hsp is not None:
        for r in D.superficies()[lambda s: s.tiene_irradiancia == 1].itertuples():
            h = hsp[hsp.superficie_id == r.superficie_id].hsp
            kp.append(kpi(f"Horas de sol pico · {r.nombre.lower()}", _num(h.mean()) if len(h) else "–", "h/día",
                          G.color_superficie(r.orden)))
    if "temperatura_ambiente" in v:
        ta = met.ta_media.dropna()
        kp.append(kpi("Temperatura ambiente (día)", _num(ta.mean()) if len(ta) else "–", "°C", G.AMBIENTE))

    hijos = [html.Div(className="rejilla-4", children=kp)] if kp else []
    if irr is not None:
        hijos += [
            tarjeta_grafica("Radiación solar a lo largo del día",
                            "Línea = promedio por hora · franja = rango donde cae la mitad de los días",
                            G.perfil_irradiancia(irr)),
            tarjeta_grafica("Horas de sol pico por día (HSP)",
                            f"Horas equivalentes de sol a 1000 W/m² que recibió cada {p['s']}",
                            G.hsp_diaria(hsp)),
            tarjeta_matriz(),
        ]
    hay_temp = bool({"temperatura_ambiente", "temperatura_modulo"} & v)
    fila = []
    if hay_temp:
        sup_t = D.superficies()[D.superficies().superficie_id.isin(D.modulos()[D.modulos().tiene_temp == 1].superficie_id)]
        donde = " · ".join(sup_t.nombre) if len(sup_t) else ""
        tit = (f"Temperatura de los {p['np']} y temperatura ambiente" if {"temperatura_ambiente", "temperatura_modulo"} <= v
               else ("Temperatura ambiente" if "temperatura_ambiente" in v else f"Temperatura de los {p['np']}"))
        fila.append(tarjeta_grafica(tit, f"{donde} · promedio por hora del día" if donde else "Promedio por hora del día",
                                    G.temperatura_modulos(tv, met)))
    if "velocidad_viento" in v:
        fila.append(tarjeta_grafica("Velocidad del viento por hora del día", "Promedio por hora", G.viento(met)))
    if "humedad_relativa" in v:
        fila.append(tarjeta_grafica("Humedad relativa por hora del día", "Promedio por hora", G.humedad(met)))
    for i in range(0, len(fila), 2):
        hijos.append(html.Div(className="rejilla-2", children=fila[i:i + 2]))
    if hay_temp:
        quien = []
        if "temperatura_modulo" in v and len(tv):
            quien.append(f"{p['np'].capitalize()} " + (f"de la {donde.lower()}" if len(sup_t) == 1 else "con sensor"))
        if "temperatura_ambiente" in v:
            quien.append("temperatura ambiente")
        quien = " y ".join(quien)
        hijos.append(tarjeta_grafica("Temperaturas en el tiempo",
                                     quien[:1].upper() + quien[1:] + " · promedio de cada hora · usa la barra inferior para acercarte",
                                     G.temperaturas_tiempo(tv, met)))
    if "velocidad_viento" in v:
        hijos.append(tarjeta_grafica("Velocidad del viento en el tiempo",
                                     "Promedio de cada hora · usa la barra inferior para acercarte",
                                     G.viento_tiempo(met)))
    if "humedad_relativa" in v:
        hijos.append(tarjeta_grafica("Humedad relativa en el tiempo",
                                     "Promedio de cada hora · usa la barra inferior para acercarte",
                                     G.humedad_tiempo(met)))
    return html.Div(className="contenedor pila", children=hijos)


# ------------------------------------------------------------------ matriz de irradiancia
ESCALA_MATRIZ = [(0, (255, 253, 245)), (250, (251, 239, 196)), (500, (246, 216, 115)),
                 (750, (240, 181, 74)), (1000, (229, 138, 46))]


def color_irradiancia(v):
    if v != v:  # NaN
        return "#ffffff"
    v = max(0.0, min(float(v), ESCALA_MATRIZ[-1][0]))
    for (a, ca), (b, cb) in zip(ESCALA_MATRIZ, ESCALA_MATRIZ[1:]):
        if v <= b:
            t = (v - a) / (b - a)
            r, g, bl = (round(x + (y - x) * t) for x, y in zip(ca, cb))
            return f"rgb({r},{g},{bl})"
    return "rgb(229,138,46)"


def _sup_irr():
    s = D.superficies()
    return s[s.tiene_irradiancia == 1]


def tarjeta_matriz():
    return html.Section(className="tarjeta tarjeta-grafica", children=[
        html.Div(className="tarjeta-cab", children=[
            html.H3("Matriz de irradiancia por hora"),
            html.P("Irradiancia promedio de cada hora (W/m²) en cada día · Σ Día = energía solar que llegó "
                   f"a la {palabras()['s']} ese día (Wh/m²)")]),
        html.Div(className="matriz-barra", children=[
            dcc.RadioItems(id="tabs-matriz", value=_sup_irr().superficie_id.iloc[0], inline=True, className="chips",
                           inputClassName="chip-input", labelClassName="chip",
                           options=[{"label": G.etiqueta_superficie(r), "value": r.superficie_id}
                                    for r in _sup_irr().itertuples()]),
            html.Button("Descargar datos", id="btn-descargar-matriz", n_clicks=0, className="btn btn-sec btn-peq"),
        ]),
        html.Div(className="matriz-info", children=[
            html.Span(id="matriz-texto"),
            html.Button("Ver todo el rango", id="btn-matriz-todo", n_clicks=0, className="enlace-btn")]),
        dcc.Loading(type="dot", color="#1b554f", children=html.Div(id="matriz-tabla", className="matriz-caja")),
        html.Div(className="matriz-leyenda", children=[
            html.Span("0 W/m²"), html.Span(className="matriz-gradiente"), html.Span("1000 W/m² o más")]),
    ])


DIAS_MATRIZ = 7   # por defecto se muestran solo los últimos días del rango (más rápido)


def tabla_matriz(ini, fin, cara, todo=False):
    """Devuelve (tabla, texto informativo, etiqueta del botón)."""
    piv = D.matriz_irradiancia(ini, fin, cara)
    if piv.empty:
        return html.Div("No hay datos de irradiancia para este rango.", className="aviso"), "", "Ver todo el rango"
    n = len(piv)
    if not todo and n > DIAS_MATRIZ:
        piv = piv.tail(DIAS_MATRIZ)
        texto = f"Mostrando los últimos {DIAS_MATRIZ} días del rango elegido."
        boton = f"Ver todo el rango ({n} días)"
    else:
        texto = f"Mostrando {n} días." if n > DIAS_MATRIZ else ""
        boton = f"Ver solo los últimos {DIAS_MATRIZ} días" if n > DIAS_MATRIZ else ""
    horas = list(piv.columns)
    cab = html.Thead(html.Tr([html.Th("Fecha")] + [html.Th(f"{h:02d}") for h in horas]
                             + [html.Th("Σ Día", className="suma")]))
    filas = []
    for fecha, fila in piv.iterrows():
        celdas = [html.Td(f_corta(fecha))]
        for h in horas:
            v = fila[h]
            celdas.append(html.Td("" if v != v else f"{v:.0f}", style={"background": color_irradiancia(v)}))
        celdas.append(html.Td(_num(fila.sum(skipna=True), 0), className="suma"))
        filas.append(html.Tr(celdas))
    return html.Table(className="matriz", children=[cab, html.Tbody(filas)]), texto, boton


def csv_matriz(ini, fin, cara):
    piv = D.matriz_irradiancia(ini, fin, cara)
    if piv.empty:
        return None
    out = piv.round(1)
    out.columns = [f"{h:02d}:00" for h in out.columns]
    out["Suma_dia_Wh_m2"] = piv.sum(axis=1, skipna=True).round(1)
    out.index.name = "fecha"
    return "\ufeff" + out.reset_index().to_csv(sep=";", decimal=",", index=False)


# =================================================================== ENERGÍA
def _barras_html(filas, unidad, dec=0):
    if not filas:
        return html.Div()
    mx = max(v for _, v, _ in filas) or 1
    return html.Div(className="barras-h", children=[
        html.Div(className="barra-fila", children=[
            html.Div(n, className="barra-nom"),
            html.Div(className="barra-pista", children=html.Div(
                className="barra-relleno", style={"width": f"{100 * v / mx:.0f}%", "background": c})),
            html.Div([_num(v, dec), html.Span(f" {unidad}", className="kpi-uni")], className="barra-val"),
        ]) for n, v, c in filas])


def _sin_seleccion():
    return html.Div(className="contenedor", children=aviso(f"Elige al menos un {palabras()['n']} en los filtros."))


def energia(f):
    ini, fin, ids = f["ini"], f["fin"], f["modulos"]
    p = palabras()
    if not ids:
        return _sin_seleccion()
    en = D.energia_dia(ini, fin, ids)
    tarjetas, filas = [], []
    for _, nom, col, _a, d in G.series_modulos(en, ids):
        d = d.energia_wh.dropna()
        tarjetas.append(html.Div(className="tarjeta kpi kpi-vidrio", style={"borderTopColor": col}, children=[
            html.Div(nom, className="kpi-nombre"),
            html.Div("Energía total", className="kpi-etq"),
            html.Div(className="kpi-val", children=[_num(d.sum() / 1000, 2) if len(d) else "–",
                                                     html.Span(" kWh", className="kpi-uni")]),
            html.Div(className="kpi-pie", children=[
                html.Span(["Promedio ", html.B(f"{_num(d.mean(), 0)} Wh/día" if len(d) else "–")]),
                html.Span(f"{len(d)} días")]),
        ]))
        if len(d):
            filas.append((nom, d.mean(), col))
    nota = None
    if len(filas) >= 2:
        filas_o = sorted(filas, key=lambda x: -x[1])
        r = filas_o[0][1] / filas_o[-1][1] if filas_o[-1][1] else 0
        mayor, menor = filas_o[0][0], filas_o[-1][0]
        if p["n"] == "vidrio":
            mayor, menor = mayor.lower(), menor.lower()
        texto = f"En este periodo, el {mayor} generó {_num(r, 1)} veces lo del {menor}."
        if p["n"] == "vidrio":
            texto += " Entre más oscuro el vidrio, más luz convierte en electricidad y menos deja pasar."
        nota = html.P(texto, className="nota")
    return html.Div(className="contenedor pila", children=[
        html.Div(className="rejilla-4", children=tarjetas),
        tarjeta_grafica(f"Energía diaria por {p['n']}", _nombre_superficie(f["cara"]), G.energia_diaria(en)),
        html.Div(className="rejilla-2", children=[
            tarjeta_grafica("Energía acumulada", "Suma día a día en el periodo elegido", G.energia_acumulada(en)),
            html.Section(className="tarjeta tarjeta-grafica", children=[
                html.Div(className="tarjeta-cab", children=[html.H3("Energía promedio por día"),
                                                            html.P("Promedio en el periodo elegido")]),
                _barras_html(filas, "Wh/día"), nota]),
        ]),
    ])


# =================================================================== DESEMPEÑO
def desempeno(f):
    ini, fin, ids = f["ini"], f["fin"], f["modulos"]
    p = palabras()
    if not ids:
        return _sin_seleccion()
    sup = D.superficies()
    con_irr = bool(sup[sup.superficie_id == f["cara"]].tiene_irradiancia.iloc[0])
    iv = D.iv_hora(ini, fin, ids)
    disp = D.dispersion(ini, fin, ids) if con_irr else None
    tarjetas, filas = [], []
    for _, nom, col, area, d in G.series_modulos(iv, ids):
        p12 = d[d.hora == 12].p_media.mean() / area if len(d) else float("nan")
        ga = d.ga_ef.sum()
        ef = 100 * d.p_ef.sum() / ga if con_irr and ga > 0 else float("nan")
        val = [html.Div([html.Div("Potencia 12:00", className="kpi-etq"),
                         html.Div(className="kpi-val kpi-val-s", children=[
                             _num(p12) if p12 == p12 else "–", html.Span(" W/m²", className="kpi-uni")])])]
        if con_irr:
            val.append(html.Div([html.Div("Eficiencia media", className="kpi-etq"),
                                 html.Div(className="kpi-val kpi-val-s", children=[
                                     _num(ef) if ef == ef else "–", html.Span(" %", className="kpi-uni")])]))
        tarjetas.append(html.Div(className="tarjeta kpi kpi-vidrio", style={"borderTopColor": col}, children=[
            html.Div(nom, className="kpi-nombre"), html.Div(className="kpi-doble", children=val)]))
        if ef == ef:
            filas.append((nom, ef, col))
    graficas = [tarjeta_grafica("Potencia a lo largo del día", "Promedio por hora", G.perfil_potencia(iv))]
    if con_irr:
        graficas += [
            tarjeta_grafica("Potencia según la radiación solar",
                            f"Cada punto es el promedio de {C.DISPERSION_MINUTOS} minutos de medición",
                            G.potencia_vs_irradiancia(disp)),
            tarjeta_grafica("Eficiencia a lo largo del día", "Promedio por hora", G.perfil_eficiencia(iv)),
            html.Section(className="tarjeta tarjeta-grafica", children=[
                html.Div(className="tarjeta-cab", children=[html.H3(f"Eficiencia media por {p['n']}"),
                                                            html.P("Promedio del periodo elegido")]),
                _barras_html(filas, "%", 1)]),
        ]
    hijos = [html.Div(className="rejilla-4", children=tarjetas), html.Div(className="rejilla-2", children=graficas)]
    if not con_irr:
        hijos.append(aviso(f"Esta {p['s']} no tiene sensor de irradiancia: no se puede calcular la eficiencia."))
    return html.Div(className="contenedor pila", children=hijos)
