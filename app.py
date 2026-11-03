"""
Plataforma de monitoreo fotovoltaico · Proyecto Integra

Muestra la base data/visor.db (generada con procesamiento/procesar.py).

Ejecutar en el computador:
    python app.py            ->  abrir http://127.0.0.1:8050

En un servidor (producción):
    gunicorn app:server
"""
import os

import dash
from dash import ALL, Input, Output, State, ctx, dcc, html, no_update

from plataforma import datos as D
from plataforma import paginas as P
from plataforma import resumen_sumicol
from plataforma.componentes import (barra_filtros, encabezado, meses_disponibles, filtro_modulos, paginas, pie,
                                    rango_texto, rangos_rapidos)

_META = D.metadatos()
app = dash.Dash(
    __name__,
    title="Visor BIPV · Proyecto Integra" if D.es_resumen_fijo() else f"{_META['instalacion']} · Proyecto Integra",
    update_title=None,
    suppress_callback_exceptions=True,
    compress=True,   # comprime las respuestas (flask-compress): la página carga más rápido
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"},
               {"name": "description", "content": f"Datos históricos · {_META['instalacion']} · Proyecto Integra"}],
)
server = app.server


def layout():
    meta = D.metadatos()
    todo = {"rango": "Todo el proyecto", "ini": meta["fecha_inicio"], "fin": meta["fecha_fin"]}
    return html.Div(className="app", children=[
        dcc.Location(id="url"),
        dcc.Store(id="fechas", data=todo, storage_type="session"),
        dcc.Store(id="borrador", data=todo),
        dcc.Download(id="descarga"),
        dcc.Download(id="descarga-exp"),
        encabezado(meta),
        html.Div(id="banda", className="banda", children=html.Div(className="contenedor banda-int", children=[
            html.Div([html.H1(id="titulo"), html.P(id="subtitulo")]),
            barra_filtros(meta),
        ])),
        dcc.Loading(type="circle", color="#1b554f", delay_show=250,
                    children=html.Main(id="contenido", className="contenido")),
        pie(),
    ])


app.layout = layout


# ------------------------------------------------------------------ navegación
def NOTA_FILTROS():
    """Los datos de Sumicol se prepararon con una ventana de 5:00 a 19:00; las demás bases se muestran tal cual."""
    return "Datos filtrados de 5:00 a 19:00" if D.es_resumen_fijo() else ""
def _ruta(ruta):
    rutas = [r for r, _ in paginas()]
    return ruta if ruta in rutas else rutas[0]


@app.callback(
    Output({"type": "nav", "index": ALL}, "className"),
    Output("banda", "style"), Output("titulo", "children"), Output("subtitulo", "children"),
    Output("nota-filtros", "children"), Output("grupo-cara", "className"), Output("grupo-modulos", "className"),
    Input("url", "pathname"),
)
def navegacion(ruta):
    ruta = _ruta(ruta)
    clases = ["nav-link activo" if r == ruta else "nav-link" for r, _ in paginas()]
    if ruta == "/":
        return clases, {"display": "none"}, "", "", "", "grupo-filtro", "grupo-filtro"
    tit, sub = P.titulos(ruta)
    if ruta == "/explorar":   # Explorar tiene sus propios selectores; de la barra solo quedan las fechas
        return clases, {}, tit, sub, NOTA_FILTROS(), "grupo-filtro oculto", "grupo-filtro oculto"
    cara_cls = "grupo-filtro atenuado" if ruta == "/clima" else "grupo-filtro"
    return clases, {}, tit, sub, NOTA_FILTROS(), cara_cls, "grupo-filtro"


@app.callback(
    Output("caja-modulos", "children"),
    Input("filtro-cara", "value"), State("filtro-vidrios", "value"), prevent_initial_call=True,
)
def modulos_de_la_superficie(sup, elegidos):
    """Al cambiar de superficie se conservan las mismas tecnologías elegidas (si no hay, todas)."""
    tec = D.tecnologias_de(elegidos or [])
    nuevos = D.modulos_de(sup)
    valor = list(nuevos[nuevos.tecnologia_id.isin(tec)].modulo_id) if tec else []
    # Se regenera el filtro completo: Dash 4 falla si se cambian por callback opciones con componentes
    return filtro_modulos(sup, valor or list(nuevos.modulo_id))


@app.callback(
    Output("contenido", "children"),
    Input("url", "pathname"), Input("fechas", "data"), Input("filtro-vidrios", "value"),
    State("filtro-cara", "value"),
)
def contenido(ruta, fechas, modulos, cara):
    ruta = _ruta(ruta)
    f = {"ini": fechas["ini"], "fin": fechas["fin"], "cara": cara, "modulos": list(modulos or [])}
    if ruta == "/clima":
        return P.clima(f)
    if ruta == "/energia":
        return P.energia(f)
    if ruta == "/desempeno":
        return P.desempeno(f)
    if ruta == "/explorar":
        return P.explorar(f)
    return resumen_sumicol.resumen()


# ------------------------------------------------------------------ matriz de irradiancia (Clima)
@app.callback(Output("matriz-tabla", "children"), Output("matriz-texto", "children"),
              Output("btn-matriz-todo", "children"), Output("btn-matriz-todo", "style"),
              Input("tabs-matriz", "value"), Input("fechas", "data"), Input("btn-matriz-todo", "n_clicks"))
def matriz(cara, fechas, n_todo):
    todo = bool(n_todo) and n_todo % 2 == 1
    tabla, texto, boton = P.tabla_matriz(fechas["ini"], fechas["fin"], cara, todo)
    return tabla, texto, boton, ({} if boton else {"display": "none"})


@app.callback(Output("descarga", "data"), Input("btn-descargar-matriz", "n_clicks"),
              State("tabs-matriz", "value"), State("fechas", "data"), prevent_initial_call=True)
def descargar_matriz(n, cara, fechas):
    if not n:
        return no_update
    texto = P.csv_matriz(fechas["ini"], fechas["fin"], cara)
    if texto is None:
        return no_update
    return dcc.send_string(texto, f"irradiancia_{cara}_{fechas['ini']}_a_{fechas['fin']}.csv")


# ------------------------------------------------------------------ Explorar
@app.callback(Output("exp-caja-entidades", "children"),
              Input("exp-variable", "value"), State("exp-entidades", "value"), prevent_initial_call=True)
def explorar_donde(variable, elegidos):
    # Se conserva la selección si la nueva variable se midió en los mismos lugares
    return P.filtro_entidades(variable, elegidos)


@app.callback(Output("exp-grupo-x", "style"), Input("exp-eje", "value"))
def explorar_eje(eje):
    return {} if eje == "variable" else {"display": "none"}


@app.callback(Output("exp-grafica", "figure"), Output("exp-titulo", "children"), Output("exp-subtitulo", "children"),
              Input("exp-entidades", "value"), Input("exp-eje", "value"), Input("exp-xvariable", "value"),
              Input("fechas", "data"), State("exp-variable", "value"))
def explorar_grafica(entidades, eje, xvariable, fechas, variable):
    return P.figura_explorar(variable, entidades, eje, xvariable, fechas["ini"], fechas["fin"])


@app.callback(Output("descarga-exp", "data"), Input("btn-descargar-exp", "n_clicks"),
              State("exp-variable", "value"), State("exp-entidades", "value"), State("exp-eje", "value"),
              State("exp-xvariable", "value"), State("fechas", "data"), prevent_initial_call=True)
def explorar_descargar(n, variable, entidades, eje, xvariable, fechas):
    if not n:
        return no_update
    texto = P.csv_explorar(variable, entidades, eje, xvariable, fechas["ini"], fechas["fin"])
    if texto is None:
        return no_update
    return dcc.send_string(texto, f"explorar_{variable}_{fechas['ini']}_a_{fechas['fin']}.csv")


# ------------------------------------------------------------------ selector de fechas
@app.callback(
    Output("pop-fechas", "style"),
    Input("btn-fechas", "n_clicks"), Input("btn-cancelar", "n_clicks"), Input("btn-aplicar", "n_clicks"),
    State("pop-fechas", "style"), prevent_initial_call=True,
)
def abrir_cerrar(_a, _b, _c, estilo):
    if ctx.triggered_id == "btn-fechas":
        return {} if (estilo or {}).get("display") == "none" else {"display": "none"}
    return {"display": "none"}


@app.callback(
    Output("borrador", "data"), Output("fecha-ini", "value"), Output("fecha-fin", "value"),
    Input({"type": "preset", "index": ALL}, "n_clicks"), Input({"type": "mes", "index": ALL}, "n_clicks"),
    Input("fecha-ini", "value"), Input("fecha-fin", "value"), Input("btn-fechas", "n_clicks"),
    State("fechas", "data"), State("borrador", "data"),
)
def editar_borrador(_p, _m, f_ini, f_fin, _abrir, aplicado, borrador):
    meta = D.metadatos()
    t = ctx.triggered_id
    if t is None or t == "btn-fechas":           # al cargar o al abrir: parte de lo aplicado
        b = dict(aplicado)
        return b, b["ini"], b["fin"]
    if isinstance(t, dict) and t.get("type") == "preset":
        if not ctx.triggered[0]["value"]:
            return no_update, no_update, no_update
        lbl, a, b = rangos_rapidos(meta)[t["index"]]
        return {"rango": lbl, "ini": a, "fin": b}, a, b
    if isinstance(t, dict) and t.get("type") == "mes":
        if not ctx.triggered[0]["value"]:
            return no_update, no_update, no_update
        for lbl, a, b, key in meses_disponibles(meta):
            if key == t["index"]:
                return {"rango": lbl, "ini": a, "fin": b}, a, b
    # edición manual de fechas
    if not f_ini or not f_fin:
        return no_update, no_update, no_update
    a, b = sorted([f_ini, f_fin])
    a, b = max(a, meta["fecha_inicio"]), min(b, meta["fecha_fin"])
    if (borrador or {}).get("ini") == a and borrador.get("fin") == b:
        return no_update, no_update, no_update
    return {"rango": "Personalizado", "ini": a, "fin": b}, a, b


@app.callback(
    Output({"type": "preset", "index": ALL}, "className"), Output({"type": "mes", "index": ALL}, "className"),
    Input("borrador", "data"),
)
def resaltar(b):
    meta = D.metadatos()
    pres = ["preset activo" if r[0] == b["rango"] else "preset" for r in rangos_rapidos(meta)]
    mes = ["mes activo" if m[0] == b["rango"] else "mes" for m in meses_disponibles(meta)]
    return pres, mes


@app.callback(Output("fechas", "data"), Input("btn-aplicar", "n_clicks"), State("borrador", "data"),
              prevent_initial_call=True)
def aplicar(_n, borrador):
    return borrador


@app.callback(Output("fechas-rango", "children"), Output("fechas-texto", "children"), Input("fechas", "data"))
def etiqueta_fechas(f):
    return f["rango"], rango_texto(f["ini"], f["fin"])


if __name__ == "__main__":
    app.run(debug=os.environ.get("DEBUG", "0") == "1", host="127.0.0.1",
            port=int(os.environ.get("PORT", 8050)))
