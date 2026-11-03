"""Gráficas Plotly con el estilo de la plataforma (Proyecto Integra)."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from . import config as C
from . import datos as D

# Paleta
VERDE = "#1b554f"
TEXTO = "#16302d"
TEXTO_2 = "#35504c"
REJILLA = "#e3ecea"
AMBIENTE = "#b9770e"
# Colores por posición: superficies en su orden; módulos según su posición dentro de la superficie
PALETA_SUPERFICIE = ["#1b554f", "#2f978d", "#d9a20b", "#73879a", "#8e5b9f", "#c0504d", "#4a7fb5", "#7a9a3a"]
PALETA_MODULO = ["#123c37", "#2f978d", "#d9a20b", "#73879a", "#8e5b9f", "#c0504d", "#4a7fb5", "#7a9a3a",
                 "#5c3d2e", "#e07a5f", "#3d405b", "#81b29a"]
FUENTE = "'Source Sans 3', 'Segoe UI', sans-serif"

LOCALE_ES = {
    "dictionary": {
        "Autoscale": "Autoescalar", "Box Select": "Seleccionar caja", "Download plot as a png": "Descargar como imagen",
        "Pan": "Desplazar", "Reset axes": "Restablecer ejes", "Zoom": "Zoom", "Zoom in": "Acercar",
        "Zoom out": "Alejar", "Show closest data on hover": "Dato más cercano", "Compare data on hover": "Comparar datos",
    },
    "format": {
        "days": ["Domingo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"],
        "shortDays": ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"],
        "months": ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre",
                   "Octubre", "Noviembre", "Diciembre"],
        "shortMonths": ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"],
        "date": "%d/%m/%Y", "decimal": ",", "thousands": ".",
    },
}

CONFIG = {
    "displaylogo": False,
    "locale": "es",
    "locales": {"es": LOCALE_ES},
    "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d", "toggleSpikelines"],
    "toImageButtonOptions": {"format": "png", "scale": 2, "filename": "visor_bipv"},
}

HORAS = list(range(C.HORA_INICIO, C.HORA_FIN))


def color_modulo(posicion):
    return PALETA_MODULO[int(posicion) % len(PALETA_MODULO)]


def color_superficie(orden):
    return PALETA_SUPERFICIE[int(orden) % len(PALETA_SUPERFICIE)]


def etiqueta_superficie(r, corta=False):
    """Cara superior (0°)  ·  corta: Superior (0°)."""
    nombre = r.nombre
    if corta and nombre.lower().startswith("cara "):
        nombre = nombre[5:].capitalize()
    return f"{nombre} ({r.inclinacion_deg:g}°)"


def series_modulos(df, ids=None):
    """Módulos de df (o los ids dados, aunque no tengan datos), en el orden de la plataforma:
    (id, etiqueta, color, área, datos del módulo)."""
    m = D.modulos()
    ids = df.modulo_id.unique() if ids is None else ids
    for r in m[m.modulo_id.isin(ids)].itertuples():
        yield r.modulo_id, r.etiqueta, color_modulo(r.color), r.area_m2, df[df.modulo_id == r.modulo_id]


def series_superficies(df, solo_irradiancia=False):
    s = D.superficies()
    if solo_irradiancia:
        s = s[s.tiene_irradiancia == 1]
    for r in s.itertuples():
        d = df[df.superficie_id == r.superficie_id]
        if not d.empty:
            yield r.superficie_id, etiqueta_superficie(r), color_superficie(r.orden), d


def rgba(hex_color, a):
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"


def _base(fig, y_titulo, x_titulo, alto=380, leyenda=True):
    fig.update_layout(
        height=alto,
        margin=dict(l=64, r=16, t=16, b=56),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#ffffff",
        font=dict(family=FUENTE, size=14, color=TEXTO_2),
        separators=",.",
        hovermode="x unified",
        hoverlabel=dict(font=dict(family=FUENTE, size=13), bgcolor="#ffffff", bordercolor="#dbe7e4"),
        showlegend=leyenda,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    font=dict(size=13, color=TEXTO), bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_yaxes(title=dict(text=y_titulo, font=dict(size=14, color=TEXTO_2)),
                     gridcolor=REJILLA, zeroline=False, linecolor="#9fb5b0", ticks="outside",
                     tickcolor="#c9d8d5", rangemode="tozero")
    fig.update_xaxes(title=dict(text=x_titulo, font=dict(size=14, color=TEXTO_2)),
                     showgrid=False, linecolor="#9fb5b0", ticks="outside", tickcolor="#c9d8d5")
    return fig


def _eje_horas(fig):
    fig.update_xaxes(tickmode="array", tickvals=list(range(6, 19, 2)),
                     ticktext=[f"{h}:00" for h in range(6, 19, 2)],
                     range=[C.HORA_INICIO - 0.5, C.HORA_FIN - 0.5])
    return fig


DIAS_MAX_BARRAS = 62   # con más días que esto, las series diarias se dibujan como líneas


def _serie_diaria(fig, fechas, valores, nombre, color, plantilla, barras):
    x = pd.to_datetime(pd.Series(fechas).values)
    y = pd.Series(valores).values
    if barras:
        fig.add_trace(go.Bar(x=x, y=y, name=nombre, marker_color=color, hovertemplate=plantilla))
    else:
        s = pd.Series(y, index=x)
        s = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="D"))  # huecos visibles
        fig.add_trace(go.Scatter(x=s.index, y=s.values, name=nombre, mode="lines+markers",
                                 line=dict(color=color, width=1.6), marker=dict(size=4, color=color),
                                 connectgaps=False, hovertemplate=plantilla))


def vacia(mensaje="No hay datos para los filtros elegidos.", alto=320):
    fig = go.Figure()
    fig.add_annotation(text=mensaje, showarrow=False, font=dict(size=15, color=TEXTO_2),
                       xref="paper", yref="paper", x=0.5, y=0.5)
    fig.update_layout(height=alto, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#ffffff",
                      xaxis=dict(visible=False), yaxis=dict(visible=False), margin=dict(l=16, r=16, t=16, b=16))
    return fig


def _banda(fig, x, bajo, alto, color, nombre, grupo):
    fig.add_trace(go.Scatter(x=x, y=alto, mode="lines", line=dict(width=0), hoverinfo="skip",
                             showlegend=False, legendgroup=grupo))
    fig.add_trace(go.Scatter(x=x, y=bajo, mode="lines", line=dict(width=0), fill="tonexty",
                             fillcolor=rgba(color, 0.16), hoverinfo="skip", showlegend=False,
                             legendgroup=grupo, name=nombre))


# ============================== CLIMA ==============================
def perfil_irradiancia(df):
    if df.empty:
        return vacia()
    fig = go.Figure()
    for sid, nom, col, d in series_superficies(df):
        g = d.groupby("hora").g_media
        st = pd.DataFrame({"m": g.mean(), "q1": g.quantile(0.25), "q3": g.quantile(0.75)}).reset_index()
        _banda(fig, st.hora, st.q1, st.q3, col, nom, sid)
        fig.add_trace(go.Scatter(
            x=st.hora, y=st.m, mode="lines+markers", name=nom, legendgroup=sid,
            line=dict(color=col, width=3), marker=dict(size=5),
            customdata=np.stack([st.q1, st.q3], axis=-1),
            hovertemplate="%{y:.0f} W/m² <span style='color:#4a635f'>(mitad de los días entre "
                          "%{customdata[0]:.0f} y %{customdata[1]:.0f})</span><extra></extra>"))
    _base(fig, "Irradiancia (W/m²)", "Hora del día", 400)
    return _eje_horas(fig)


def hsp_diaria(df):
    if df.empty:
        return vacia()
    fig = go.Figure()
    barras = df.fecha.nunique() <= DIAS_MAX_BARRAS
    for _, nom, col, d in series_superficies(df):
        _serie_diaria(fig, d.fecha, d.hsp, nom, col,
                      "%{y:.1f} h<extra>%{fullData.name}</extra>", barras)
    _base(fig, "HSP (horas)", "Fecha", 440)
    fig.update_layout(barmode="group", bargap=0.18, bargroupgap=0.05)
    fig.update_xaxes(tickformat="%d %b\n%Y")
    _eje_tiempo(fig, horario=False)
    return fig


def temperatura_modulos(tv, met):
    if tv.empty and met.empty:
        return vacia()
    fig = go.Figure()
    for _, nom, col, _a, d in series_modulos(tv):
        m = d.groupby("hora").t_media.mean()
        fig.add_trace(go.Scatter(x=m.index, y=m.values, mode="lines+markers", name=nom,
                                 line=dict(color=col, width=3), marker=dict(size=5),
                                 hovertemplate="%{y:.1f} °C<extra>%{fullData.name}</extra>"))
    a = met.dropna(subset=["ta_media"]).groupby("hora").ta_media.mean()
    if not a.empty:
        fig.add_trace(go.Scatter(x=a.index, y=a.values, mode="lines", name="Temperatura ambiente",
                                 line=dict(color=AMBIENTE, width=2.5, dash="dash"),
                                 hovertemplate="%{y:.1f} °C<extra>Ambiente</extra>"))
    _base(fig, "Temperatura (°C)", "Hora del día", 400)
    fig.update_yaxes(rangemode="normal")
    return _eje_horas(fig)


def _horaria(fechas, horas, valores, dec=1):
    """Serie horaria redondeada; donde faltan horas (p. ej. de noche) se inserta un solo hueco
    para que la línea se corte sin enviar horas vacías al navegador."""
    t = pd.to_datetime(pd.Series(fechas).values) + pd.to_timedelta(pd.Series(horas).values, unit="h")
    s = pd.Series(pd.Series(valores).values, index=t).groupby(level=0).mean().sort_index().round(dec)
    if s.empty:
        return s
    salto = s.index.to_series().diff() > pd.Timedelta(hours=1)
    huecos = pd.Series(np.nan, index=s.index[salto] - pd.Timedelta(minutes=30))
    return pd.concat([s, huecos]).sort_index()


def _eje_tiempo(fig, horario=True):
    """Eje de fechas con botones 7 días / 1 mes / Todo y barra inferior para acercarse."""
    fig.update_xaxes(
        tickformat="%d %b\n%Y", hoverformat="%d %b %Y · %H:00" if horario else "%d %b %Y",
        rangeslider=dict(visible=True, thickness=0.07, bgcolor="#f5f9f8", bordercolor="#dbe7e4", borderwidth=1),
        rangeselector=dict(
            buttons=[dict(count=7, label="7 días", step="day", stepmode="backward"),
                     dict(count=1, label="1 mes", step="month", stepmode="backward"),
                     dict(step="all", label="Todo")],
            x=0, y=1.0, yanchor="bottom", bgcolor="#ffffff", activecolor="#eef6f3",
            bordercolor="#b9d3ce", borderwidth=1, font=dict(size=12, color=TEXTO)))
    fig.update_layout(legend=dict(x=0, xanchor="left", y=1.1, yanchor="bottom"), margin=dict(t=64))
    return fig


def temperaturas_tiempo(tv, met):
    if tv.empty and met.dropna(subset=["ta_media"]).empty:
        return vacia()
    fig = go.Figure()
    for _, nom, col, _a, d in series_modulos(tv):
        s = _horaria(d.fecha, d.hora, d.t_media)
        fig.add_trace(go.Scatter(x=s.index, y=s.values, mode="lines", name=nom,
                                 line=dict(color=col, width=1.6), connectgaps=False,
                                 hovertemplate="%{y:.1f} °C<extra>%{fullData.name}</extra>"))
    a = met.dropna(subset=["ta_media"])
    if not a.empty:
        s = _horaria(a.fecha, a.hora, a.ta_media)
        fig.add_trace(go.Scatter(x=s.index, y=s.values, mode="lines", name="Temperatura ambiente",
                                 line=dict(color=AMBIENTE, width=1.8, dash="dot"), connectgaps=False,
                                 hovertemplate="%{y:.1f} °C<extra>Ambiente</extra>"))
    _base(fig, "Temperatura (°C)", "Fecha", 480)
    fig.update_yaxes(rangemode="normal")
    return _eje_tiempo(fig)


def viento_tiempo(met):
    d = met.dropna(subset=["viento_media"])
    if d.empty:
        return vacia()
    s = _horaria(d.fecha, d.hora, d.viento_media)
    fig = go.Figure(go.Scatter(x=s.index, y=s.values, mode="lines", name="Viento",
                               line=dict(color="#2f978d", width=1.6), connectgaps=False,
                               fill="tozeroy", fillcolor="rgba(47,151,141,0.10)",
                               hovertemplate="%{y:.1f} m/s<extra></extra>"))
    _base(fig, "Velocidad del viento (m/s)", "Fecha", 420, leyenda=False)
    return _eje_tiempo(fig)


def viento(met):
    d = met.dropna(subset=["viento_media"])
    if d.empty:
        return vacia()
    m = d.groupby("hora").viento_media.mean()
    fig = go.Figure(go.Bar(x=m.index, y=m.values, marker_color="#2f978d", name="Viento",
                           hovertemplate="%{y:.1f} m/s<extra></extra>"))
    _base(fig, "Velocidad del viento (m/s)", "Hora del día", 340, leyenda=False)
    fig.update_layout(bargap=0.3)
    return _eje_horas(fig)


def humedad_tiempo(met):
    d = met.dropna(subset=["hr_media"])
    if d.empty:
        return vacia()
    s = _horaria(d.fecha, d.hora, d.hr_media)
    fig = go.Figure(go.Scatter(x=s.index, y=s.values, mode="lines", name="Humedad relativa",
                               line=dict(color="#4a7fb5", width=1.6), connectgaps=False,
                               hovertemplate="%{y:.0f} %<extra></extra>"))
    _base(fig, "Humedad relativa (%)", "Fecha", 420, leyenda=False)
    fig.update_yaxes(range=[0, 100])
    return _eje_tiempo(fig)


def humedad(met):
    d = met.dropna(subset=["hr_media"])
    if d.empty:
        return vacia()
    m = d.groupby("hora").hr_media.mean()
    fig = go.Figure(go.Scatter(x=m.index, y=m.values, mode="lines+markers", name="Humedad relativa",
                               line=dict(color="#4a7fb5", width=3), marker=dict(size=5),
                               hovertemplate="%{y:.0f} %<extra></extra>"))
    _base(fig, "Humedad relativa (%)", "Hora del día", 340, leyenda=False)
    fig.update_yaxes(range=[0, 100])
    return _eje_horas(fig)


# ============================== ENERGÍA ==============================
def energia_diaria(df):
    if df.empty:
        return vacia()
    fig = go.Figure()
    barras = df.fecha.nunique() <= DIAS_MAX_BARRAS
    for _, nom, col, _a, d in series_modulos(df):
        _serie_diaria(fig, d.fecha, d.energia_wh, nom, col,
                      "%{y:.0f} Wh<extra>%{fullData.name}</extra>", barras)
    _base(fig, "Energía (Wh/día)", "Fecha", 460)
    fig.update_layout(barmode="group", bargap=0.18, bargroupgap=0.04)
    fig.update_xaxes(tickformat="%d %b\n%Y")
    _eje_tiempo(fig, horario=False)
    return fig


def energia_acumulada(df):
    if df.empty:
        return vacia()
    fig = go.Figure()
    for _, nom, col, _a, d in series_modulos(df):
        d = d.sort_values("fecha")
        fig.add_trace(go.Scatter(x=pd.to_datetime(d.fecha), y=d.energia_wh.cumsum() / 1000, mode="lines",
                                 name=nom, line=dict(color=col, width=3),
                                 hovertemplate="%{y:.2f} kWh<extra>%{fullData.name}</extra>"))
    _base(fig, "Energía acumulada (kWh)", "Fecha", 420)
    fig.update_xaxes(tickformat="%d %b\n%Y")
    _eje_tiempo(fig, horario=False)
    return fig


# ============================== DESEMPEÑO ==============================
def perfil_potencia(df):
    if df.empty:
        return vacia()
    fig = go.Figure()
    for _, nom, col, area, d in series_modulos(df):
        m = d.groupby("hora").p_media.mean() / area
        fig.add_trace(go.Scatter(x=m.index, y=m.values, mode="lines+markers", name=nom,
                                 line=dict(color=col, width=3), marker=dict(size=5),
                                 hovertemplate="%{y:.1f} W/m²<extra>%{fullData.name}</extra>"))
    _base(fig, "Potencia (W/m²)", "Hora del día", 360)
    return _eje_horas(fig)


def potencia_vs_irradiancia(df):
    if df.empty:
        return vacia()
    fig = go.Figure()
    for _, nom, col, area, d in series_modulos(df):
        fig.add_trace(go.Scattergl(x=d.g, y=d.p / area, mode="markers", name=nom,
                                   marker=dict(color=col, size=5, opacity=0.55),
                                   hovertemplate="%{x:.0f} W/m² → %{y:.1f} W/m²<extra>%{fullData.name}</extra>"))
    _base(fig, "Potencia (W/m²)", "Irradiancia (W/m²)", 360)
    fig.update_layout(hovermode="closest", legend=dict(itemsizing="constant"))
    fig.update_xaxes(showgrid=True, gridcolor=REJILLA, rangemode="tozero")
    return fig


def perfil_eficiencia(df):
    d = df[df.ga_ef > 0]
    if d.empty:
        return vacia()
    fig = go.Figure()
    for _, nom, col, _a, x in series_modulos(d):
        s = x.groupby("hora")[["p_ef", "ga_ef"]].sum()
        e = 100 * s.p_ef / s.ga_ef
        fig.add_trace(go.Scatter(x=e.index, y=e.values, mode="lines+markers", name=nom,
                                 line=dict(color=col, width=3), marker=dict(size=5),
                                 hovertemplate="%{y:.1f} %<extra>%{fullData.name}</extra>"))
    _base(fig, "Eficiencia (%)", "Hora del día", 360)
    return _eje_horas(fig)


# ============================== EXPLORAR ==============================
PALETA_EXPLORAR = PALETA_MODULO


def _color_i(i):
    return PALETA_EXPLORAR[i % len(PALETA_EXPLORAR)]


def _eje_y(nombre, unidad):
    return f"{nombre} ({unidad})" if unidad else nombre


def explorar_tiempo(series, nombre, unidad, dec=2):
    """series: [(etiqueta, df fecha/hora/valor, color)]."""
    if not any(len(d) for _, d, _c in series):
        return vacia()
    fig = go.Figure()
    u = f" {unidad}" if unidad else ""
    for et, d, col in series:
        if d.empty:
            continue
        s = _horaria(d.fecha, d.hora, d.valor, dec)
        fig.add_trace(go.Scatter(x=s.index, y=s.values, mode="lines", name=et, connectgaps=False,
                                 line=dict(color=col, width=1.6),
                                 hovertemplate=f"%{{y:.{dec}f}}{u}<extra>%{{fullData.name}}</extra>"))
    _base(fig, _eje_y(nombre, unidad), "Fecha", 480)
    fig.update_yaxes(rangemode="normal")
    return _eje_tiempo(fig)


def explorar_perfil(series, nombre, unidad, dec=2):
    if not any(len(d) for _, d, _c in series):
        return vacia()
    fig = go.Figure()
    u = f" {unidad}" if unidad else ""
    for et, d, col in series:
        if d.empty:
            continue
        g = d.groupby("hora").valor
        st = pd.DataFrame({"m": g.mean(), "q1": g.quantile(0.25), "q3": g.quantile(0.75)}).reset_index()
        _banda(fig, st.hora, st.q1, st.q3, col, et, et)
        fig.add_trace(go.Scatter(x=st.hora, y=st.m, mode="lines+markers", name=et, legendgroup=et,
                                 line=dict(color=col, width=3), marker=dict(size=5),
                                 hovertemplate=f"%{{y:.{dec}f}}{u}<extra>%{{fullData.name}}</extra>"))
    _base(fig, _eje_y(nombre, unidad), "Hora del día", 440)
    fig.update_yaxes(rangemode="normal")
    return _eje_horas(fig)


def explorar_dispersion(pares, xnombre, xunidad, ynombre, yunidad, dec=2):
    """pares: [(etiqueta, df con x, y, color)]."""
    if not any(len(d) for _, d, _c in pares):
        return vacia("No hay datos de las dos variables en las mismas horas.")
    fig = go.Figure()
    xu, yu = (f" {xunidad}" if xunidad else ""), (f" {yunidad}" if yunidad else "")
    for et, d, col in pares:
        if d.empty:
            continue
        fig.add_trace(go.Scattergl(x=d.x, y=d.y, mode="markers", name=et,
                                   marker=dict(color=col, size=5, opacity=0.55),
                                   hovertemplate=f"%{{x:.{dec}f}}{xu} → %{{y:.{dec}f}}{yu}<extra>%{{fullData.name}}</extra>"))
    _base(fig, _eje_y(ynombre, yunidad), _eje_y(xnombre, xunidad), 480)
    fig.update_layout(hovermode="closest", legend=dict(itemsizing="constant"))
    fig.update_xaxes(showgrid=True, gridcolor=REJILLA)
    fig.update_yaxes(rangemode="normal")
    return fig
