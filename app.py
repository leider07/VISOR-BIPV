"""
Plataforma de monitoreo fotovoltaico · Proyecto Integra

Muestra la base data/visor.db (generada con procesamiento/procesar.py). En la pestaña «Tus datos»
cada visitante puede cargar su propia base y verla él solo (se guarda temporalmente en el servidor).

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
from plataforma import tus_datos as T
from plataforma.componentes import (aviso_base_propia, barra_filtros, encabezado, meses_disponibles, filtro_modulos,
                                    paginas, pie, rango_texto, rangos_rapidos)

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


def marco(propia=False):
    """Encabezado, filtros, contenido y pie de la base activa (Sumicol o la que cargó el visitante)."""
    meta = D.metadatos()
    todo = {"rango": "Todo el proyecto", "ini": meta["fecha_inicio"], "fin": meta["fecha_fin"]}
    return [
        dcc.Store(id="fechas", data=todo),
        dcc.Store(id="borrador", data=todo),
        encabezado(meta),
        aviso_base_propia(meta) if propia else None,
        html.Div(id="banda", className="banda", children=html.Div(className="contenedor banda-int", children=[
            html.Div([html.H1(id="titulo"), html.P(id="subtitulo")]),
            barra_filtros(meta),
        ])),
        dcc.Loading(type="circle", color="#1b554f", delay_show=250,
                    children=html.Main(id="contenido", className="contenido")),
        pie(),
    ]


def layout():
    D.usar(None)
    return html.Div(className="app", children=[
        dcc.Location(id="url"),
        dcc.Store(id="base", storage_type="session"),    # código de la base cargada por el visitante
        dcc.Download(id="descarga"),
        dcc.Download(id="descarga-exp"),
        dcc.Download(id="descarga-plantilla"),
        html.Div(id="marco", children=marco()),
    ])


app.layout = layout


@app.callback(Output("marco", "children"), Input("base", "data"))
def armar_marco(base):
    """Al cargar (o quitar) una base propia se rearma toda la página con esa base."""
    if not base:
        if ctx.triggered_id is None:
            return no_update            # primera carga sin base propia: ya está la de Sumicol
        D.usar(None)
        return marco()
    return marco(propia=D.usar(base))


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
    Output("barra-filtros", "style"),
    Input("url", "pathname"), Input("fechas", "data"), State("base", "data"),
)
def navegacion(ruta, _fechas, base):
    D.usar(base)
    ruta = _ruta(ruta)
    # Las clases se calculan para los enlaces que hay en pantalla (al cambiar de base puede quedar un instante
    # el menú de la base anterior)
    clases = ["nav-link activo" if o["id"]["index"] == ruta else "nav-link" for o in ctx.outputs_list[0]]
    if ruta == "/":
        return clases, {"display": "none"}, "", "", "", "grupo-filtro", "grupo-filtro", {}
    if ruta == "/datos":
        return (clases, {}, "Visualiza los datos de tu instalación",
                "Crea la plantilla, llénala con tus mediciones y cárgala para verla en la plataforma.",
                "", "grupo-filtro", "grupo-filtro", {"display": "none"})
    tit, sub = P.titulos(ruta)
    if ruta == "/explorar":   # Explorar tiene sus propios selectores; de la barra solo quedan las fechas
        return clases, {}, tit, sub, NOTA_FILTROS(), "grupo-filtro oculto", "grupo-filtro oculto", {}
    cara_cls = "grupo-filtro atenuado" if ruta == "/clima" else "grupo-filtro"
    return clases, {}, tit, sub, NOTA_FILTROS(), cara_cls, "grupo-filtro", {}


@app.callback(
    Output("caja-modulos", "children"),
    Input("filtro-cara", "value"), State("filtro-vidrios", "value"), State("base", "data"), prevent_initial_call=True,
)
def modulos_de_la_superficie(sup, elegidos, base):
    D.usar(base)
    """Al cambiar de superficie se conservan las mismas tecnologías elegidas (si no hay, todas)."""
    tec = D.tecnologias_de(elegidos or [])
    nuevos = D.modulos_de(sup)
    valor = list(nuevos[nuevos.tecnologia_id.isin(tec)].modulo_id) if tec else []
    # Se regenera el filtro completo: Dash 4 falla si se cambian por callback opciones con componentes
    return filtro_modulos(sup, valor or list(nuevos.modulo_id))


@app.callback(
    Output("contenido", "children"),
    Input("url", "pathname"), Input("fechas", "data"), Input("filtro-vidrios", "value"),
    State("filtro-cara", "value"), State("base", "data"),
)
def contenido(ruta, fechas, modulos, cara, base):
    D.usar(base)
    ruta = _ruta(ruta)
    # Al cambiar de base, los filtros pueden traer por un instante valores de la base anterior
    sups = list(D.superficies().superficie_id)
    if cara not in sups:
        cara = sups[0]
    validos = list(D.modulos_de(cara).modulo_id)
    filtrados = [m for m in (modulos or []) if m in validos]
    modulos = filtrados if (filtrados or modulos == []) else validos
    if ruta == "/datos":
        return T.pagina(base)
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
              Input("tabs-matriz", "value"), Input("fechas", "data"), Input("btn-matriz-todo", "n_clicks"),
              State("base", "data"))
def matriz(cara, fechas, n_todo, base):
    D.usar(base)
    todo = bool(n_todo) and n_todo % 2 == 1
    tabla, texto, boton = P.tabla_matriz(fechas["ini"], fechas["fin"], cara, todo)
    return tabla, texto, boton, ({} if boton else {"display": "none"})


@app.callback(Output("descarga", "data"), Input("btn-descargar-matriz", "n_clicks"),
              State("tabs-matriz", "value"), State("fechas", "data"), State("base", "data"), prevent_initial_call=True)
def descargar_matriz(n, cara, fechas, base):
    D.usar(base)
    if not n:
        return no_update
    texto = P.csv_matriz(fechas["ini"], fechas["fin"], cara)
    if texto is None:
        return no_update
    return dcc.send_string(texto, f"irradiancia_{cara}_{fechas['ini']}_a_{fechas['fin']}.csv")


# ------------------------------------------------------------------ Explorar
@app.callback(Output("exp-caja-entidades", "children"),
              Input("exp-variable", "value"), State("exp-entidades", "value"), State("base", "data"),
              prevent_initial_call=True)
def explorar_donde(variable, elegidos, base):
    D.usar(base)
    # Se conserva la selección si la nueva variable se midió en los mismos lugares
    return P.filtro_entidades(variable, elegidos)


@app.callback(Output("exp-grupo-x", "style"), Input("exp-eje", "value"))
def explorar_eje(eje):
    return {} if eje == "variable" else {"display": "none"}


@app.callback(Output("exp-grafica", "figure"), Output("exp-titulo", "children"), Output("exp-subtitulo", "children"),
              Input("exp-entidades", "value"), Input("exp-eje", "value"), Input("exp-xvariable", "value"),
              Input("fechas", "data"), State("exp-variable", "value"), State("base", "data"))
def explorar_grafica(entidades, eje, xvariable, fechas, variable, base):
    D.usar(base)
    return P.figura_explorar(variable, entidades, eje, xvariable, fechas["ini"], fechas["fin"])


@app.callback(Output("descarga-exp", "data"), Input("btn-descargar-exp", "n_clicks"),
              State("exp-variable", "value"), State("exp-entidades", "value"), State("exp-eje", "value"),
              State("exp-xvariable", "value"), State("fechas", "data"), State("base", "data"), prevent_initial_call=True)
def explorar_descargar(n, variable, entidades, eje, xvariable, fechas, base):
    D.usar(base)
    if not n:
        return no_update
    texto = P.csv_explorar(variable, entidades, eje, xvariable, fechas["ini"], fechas["fin"])
    if texto is None:
        return no_update
    return dcc.send_string(texto, f"explorar_{variable}_{fechas['ini']}_a_{fechas['fin']}.csv")


# ------------------------------------------------------------------ Tus datos
@app.callback(Output("form-modulos", "dropdown"), Input("form-superficies", "data"), Input("form-tecnologias", "data"))
def desplegables_modulos(sup, tec):
    return T.desplegables_modulos(sup, tec)


@app.callback(Output("form-sensores", "dropdown"), Input("form-superficies", "data"), Input("form-modulos", "data"),
              Input("form-adicionales", "data"))
def desplegables_sensores(sup, mod, adic):
    return T.desplegables_sensores(sup, mod, adic)


def _agregar_fila(tabla):
    @app.callback(Output(f"form-{tabla}", "data", allow_duplicate=True), Input(f"agregar-{tabla}", "n_clicks"),
                  State(f"form-{tabla}", "data"), prevent_initial_call=True)
    def agregar(n, filas):
        return (filas or []) + [T._fila_vacia(tabla)] if n else no_update
    return agregar


for _t in T.TABLAS:
    _agregar_fila(_t)


@app.callback(Output("caja-formulario", "children"), Input("btn-ejemplo", "n_clicks"), prevent_initial_call=True)
def llenar_ejemplo(n):
    return T.formulario(T.EJEMPLO) if n else no_update


@app.callback(Output("descarga-plantilla", "data"), Output("form-resultado", "children"),
              Input("btn-generar", "n_clicks"),
              State("form-nombre", "value"), State("form-descripcion", "value"), State("form-responsable", "value"),
              State("form-ciudad", "value"), State("form-pais", "value"), State("form-tecnologias", "data"),
              State("form-superficies", "data"), State("form-modulos", "data"), State("form-electricas", "value"),
              State("form-adicionales", "data"), State("form-sensores", "data"), prevent_initial_call=True)
def generar_plantilla(n, *campos):
    if not n:
        return no_update, no_update
    d = T.datos_formulario(*campos)
    contenido, resultado = T.generar_plantilla(d)
    if contenido is None:
        return no_update, resultado
    nombre = "".join(ch if ch.isalnum() else "_" for ch in (d["instalacion"]["nombre"] or "instalacion")).strip("_")
    return dcc.send_bytes(contenido, f"plantilla_{nombre.lower()}.db"), resultado


@app.callback(Output("descarga-plantilla", "data", allow_duplicate=True),
              Input("btn-guia", "n_clicks"), Input("btn-plantilla-vacia", "n_clicks"), prevent_initial_call=True)
def descargar_formato(_g, _p):
    if not ctx.triggered or not ctx.triggered[0]["value"]:
        return no_update
    nombre = "guia_formato.md" if ctx.triggered_id == "btn-guia" else "plantilla_v1.1.db"
    return dcc.send_file(str(T.C.RAIZ / "formato" / nombre))


@app.callback(Output("base", "data"), Output("carga-resultado", "children"),
              Input("carga-archivo", "contents"), State("carga-archivo", "filename"), prevent_initial_call=True)
def cargar_base(contenido, nombre):
    token, resultado = T.cargar(contenido, nombre)
    return (token if token else no_update), resultado


@app.callback(Output("base", "data", allow_duplicate=True), Input({"type": "volver", "index": ALL}, "n_clicks"),
              prevent_initial_call=True)
def volver_a_sumicol(clics):
    return None if any(clics or []) else no_update


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
    State("fechas", "data"), State("borrador", "data"), State("base", "data"),
)
def editar_borrador(_p, _m, f_ini, f_fin, _abrir, aplicado, borrador, base):
    D.usar(base)
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
    Input("borrador", "data"), State("base", "data"),
)
def resaltar(b, base):
    D.usar(base)
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
