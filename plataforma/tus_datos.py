"""Pestaña «Tus datos»: crear la plantilla del formato de carga y cargar una base para verla."""
import base64
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid

from dash import dash_table, dcc, html

from procesamiento import plantilla as PL
from procesamiento.validar_bd import Validador

from . import config as C
from . import datos as D

# ------------------------------------------------------------------ tablas del formulario
NOMBRES_AMBIENTALES = {
    "irradiancia": "Irradiancia (W/m²)", "temperatura_ambiente": "Temperatura ambiente (°C)",
    "temperatura_modulo": "Temperatura de módulo (°C)", "humedad_relativa": "Humedad relativa (%)",
    "velocidad_viento": "Velocidad del viento (m/s)",
}

TABLAS = {
    "tecnologias": [("tecnologia_id", "Código *", "text"), ("nombre", "Nombre *", "text"), ("tipo", "Tipo *", "lista"),
                    ("potencia_stc_w", "Potencia STC (W) *", "numeric"), ("area_m2", "Área (m²) *", "numeric"),
                    ("transmitancia_pct", "Transmitancia (%)", "numeric"), ("fabricante", "Fabricante", "text"),
                    ("modelo", "Modelo", "text")],
    "superficies": [("superficie_id", "Código *", "text"), ("nombre", "Nombre *", "text"),
                    ("inclinacion_deg", "Inclinación (°) *", "numeric"), ("orientacion", "Orientación", "lista"),
                    ("descripcion", "Descripción", "text")],
    "cronograma": [("superficie_id", "Superficie *", "lista"), ("desde", "Desde *", "text"),
                   ("hasta", "Hasta", "text"), ("orientacion", "Orientación *", "lista"),
                   ("inclinacion_deg", "Inclinación (°)", "numeric")],
    "modulos": [("modulo_id", "Código *", "text"), ("superficie_id", "Superficie *", "lista"),
                ("tecnologia_id", "Tecnología *", "lista"), ("nombre", "Nombre para mostrar", "text")],
    "adicionales": [("variable_id", "Código *", "text"), ("nombre", "Nombre *", "text"), ("unidad", "Unidad", "text"),
                    ("tipo", "Tipo *", "lista"), ("agregacion", "Resumen por hora", "lista")],
    "sensores": [("sensor_id", "Columna *", "text"), ("variable_id", "Mide *", "lista"),
                 ("superficie_id", "Superficie (irradiancia)", "lista"),
                 ("modulo_id", "Módulo (temperatura de módulo)", "lista"), ("modelo", "Modelo", "text")],
}
AYUDAS = {
    "tecnologias": "Cada tipo de módulo. La potencia STC y el área se usan para calcular la eficiencia.",
    "superficies": "Caras, fachadas o cubiertas donde están los módulos. Inclinación: 0° horizontal, 90° vertical.",
    "modulos": "Cada módulo con medición eléctrica: en qué superficie está y de qué tecnología es.",
    "cronograma": "Solo si alguna superficie se giró o cambió de inclinación: una fila por superficie y periodo. "
                  "Fechas AAAA-MM-DD (o AAAA-MM-DD HH:MM:SS); deja «Hasta» vacío si siguió así hasta el final. "
                  "Si ninguna superficie se movió, deja esta tabla vacía.",
    "adicionales": "La potencia máxima es obligatoria y ya viene incluida. Agrega aquí las demás variables que vas a "
                   "entregar: eléctricas (voltaje de circuito abierto, corriente de cortocircuito, fill factor…) o "
                   "ambientales que no estén en la lista de sensores (lluvia, dirección del viento…). "
                   "Se ven en la pestaña Explorar. Si el resumen por hora se deja vacío, se usa el promedio.",
    "sensores": "Cada columna de la tabla de mediciones ambientales. La irradiancia lleva su superficie; "
                "la temperatura de módulo, su módulo.",
}
TITULOS = {"tecnologias": "Tecnologías", "superficies": "Superficies", "modulos": "Módulos",
           "adicionales": "Otras variables", "sensores": "Sensores ambientales",
           "cronograma": "Cronograma de orientaciones (opcional)"}

EJEMPLO = {
    "instalacion": {"nombre": "Techo solar de ejemplo", "descripcion": "Dos tecnologías en un techo y una fachada",
                    "responsable": "Grupo de investigación", "ciudad": "Medellín", "pais": "Colombia"},
    "tecnologias": [{"tecnologia_id": "MONO", "nombre": "Monocristalino 450 W", "tipo": "c-Si mono",
                     "potencia_stc_w": 450, "area_m2": 2.0},
                    {"tecnologia_id": "CIGS", "nombre": "CIGS 150 W", "tipo": "CIGS", "potencia_stc_w": 150,
                     "area_m2": 1.1}],
    "superficies": [{"superficie_id": "techo", "nombre": "Techo", "inclinacion_deg": 10, "orientacion": "Sur"},
                    {"superficie_id": "fachada", "nombre": "Fachada oeste", "inclinacion_deg": 90,
                     "orientacion": "Oeste"}],
    "modulos": [{"modulo_id": "M1", "superficie_id": "techo", "tecnologia_id": "MONO"},
                {"modulo_id": "C1", "superficie_id": "techo", "tecnologia_id": "CIGS"},
                {"modulo_id": "F1", "superficie_id": "fachada", "tecnologia_id": "MONO"}],
    "adicionales": [{"variable_id": "voc_v", "nombre": "Voltaje de circuito abierto", "unidad": "V",
                     "tipo": "electrica", "agregacion": "promedio"},
                    {"variable_id": "isc_a", "nombre": "Corriente de cortocircuito", "unidad": "A",
                     "tipo": "electrica", "agregacion": "promedio"},
                    {"variable_id": "ff", "nombre": "Fill factor", "unidad": "", "tipo": "electrica",
                     "agregacion": "promedio"}],
    "sensores": [{"sensor_id": "G_techo", "variable_id": "irradiancia", "superficie_id": "techo", "modelo": "SMP10"},
                 {"sensor_id": "T_amb", "variable_id": "temperatura_ambiente"},
                 {"sensor_id": "T_M1", "variable_id": "temperatura_modulo", "modulo_id": "M1"}],
}


def _fila_vacia(tabla):
    return {c: "" for c, _, _ in TABLAS[tabla]}


def _tabla(tabla, filas=None):
    cols = []
    for c, nombre, tipo in TABLAS[tabla]:
        col = {"id": c, "name": nombre}
        if tipo == "numeric":
            col["type"] = "numeric"
        if tipo == "lista":
            col["presentation"] = "dropdown"
        cols.append(col)
    return dash_table.DataTable(
        id=f"form-{tabla}", columns=cols, data=filas or [_fila_vacia(tabla)], editable=True, row_deletable=True,
        dropdown=desplegables_fijos(tabla), css=[{"selector": ".Select-menu-outer", "rule": "display: block !important"}],
        style_table={"overflowX": "auto"}, style_cell={"fontFamily": "'Source Sans 3', sans-serif", "fontSize": 15,
                                                        "padding": "8px 10px", "textAlign": "left", "minWidth": 110},
        style_header={"fontFamily": "Montserrat, sans-serif", "fontSize": 12, "fontWeight": 700,
                      "background": "#eef6f3", "color": "#1b554f"},
        style_data={"background": "#fff"}, page_action="none")


def _opciones(valores, etiquetas=None):
    etiquetas = etiquetas or {}
    return [{"label": etiquetas.get(v, v), "value": v} for v in valores]


def desplegables_fijos(tabla):
    if tabla == "tecnologias":
        return {"tipo": {"options": _opciones(PL.TIPOS_TECNOLOGIA)}}
    if tabla == "superficies":
        return {"orientacion": {"options": _opciones(PL.ORIENTACIONES)}}
    if tabla == "cronograma":
        return {"orientacion": {"options": _opciones(PL.ORIENTACIONES)}}
    if tabla == "adicionales":
        return {"tipo": {"options": _opciones(["electrica", "ambiental"], {"electrica": "Eléctrica",
                                                                           "ambiental": "Ambiental"})},
                "agregacion": {"options": _opciones(PL.AGREGACIONES, {"minimo": "mínimo", "maximo": "máximo"})}}
    return {}


def desplegables_modulos(superficies, tecnologias):
    sup = [f.get("superficie_id") for f in superficies or [] if f.get("superficie_id")]
    tec = [f.get("tecnologia_id") for f in tecnologias or [] if f.get("tecnologia_id")]
    return {"superficie_id": {"options": _opciones(sup)}, "tecnologia_id": {"options": _opciones(tec)}}


def desplegables_cronograma(superficies):
    sup = [f.get("superficie_id") for f in superficies or [] if f.get("superficie_id")]
    return {"superficie_id": {"options": _opciones(sup)}, "orientacion": {"options": _opciones(PL.ORIENTACIONES)}}


def desplegables_sensores(superficies, modulos, adicionales):
    amb = list(NOMBRES_AMBIENTALES) + [f.get("variable_id") for f in adicionales or []
                                       if f.get("tipo") == "ambiental" and f.get("variable_id")]
    etq = dict(NOMBRES_AMBIENTALES)
    etq.update({f.get("variable_id"): f"{f.get('nombre') or f.get('variable_id')} (adicional)"
                for f in adicionales or [] if f.get("variable_id")})
    sup = [""] + [f.get("superficie_id") for f in superficies or [] if f.get("superficie_id")]
    mod = [""] + [f.get("modulo_id") for f in modulos or [] if f.get("modulo_id")]
    return {"variable_id": {"options": _opciones(amb, etq)},
            "superficie_id": {"options": _opciones(sup, {"": "—"})},
            "modulo_id": {"options": _opciones(mod, {"": "—"})}}


# ------------------------------------------------------------------ página
def _campo(id_, etiqueta, valor="", obligatorio=False):
    return html.Div(className="campo", children=[
        html.Label(etiqueta + (" *" if obligatorio else ""), htmlFor=id_),
        dcc.Input(id=id_, value=valor, type="text", className="input-texto", debounce=False)])


def _bloque_tabla(tabla, filas=None):
    return html.Div(className="form-bloque", children=[
        html.Div(className="form-bloque-cab", children=[
            html.H4(TITULOS[tabla]), html.P(AYUDAS[tabla], className="nota")]),
        _tabla(tabla, filas),
        html.Button("+ Agregar fila", id=f"agregar-{tabla}", n_clicks=0, className="enlace-btn")])


def formulario(d=None):
    d = d or {}
    inst = d.get("instalacion", {})
    return html.Div(id="formulario", className="pila-form", children=[
        html.Div(className="form-bloque", children=[
            html.Div(className="form-bloque-cab", children=[html.H4("Instalación"),
                                                            html.P("Datos generales del proyecto.", className="nota")]),
            html.Div(className="rejilla-campos", children=[
                _campo("form-nombre", "Nombre", inst.get("nombre", ""), True),
                _campo("form-descripcion", "Descripción", inst.get("descripcion", "")),
                _campo("form-responsable", "Responsable", inst.get("responsable", "")),
                _campo("form-ciudad", "Ciudad", inst.get("ciudad", "")),
                _campo("form-pais", "País", inst.get("pais", ""))])]),
        _bloque_tabla("tecnologias", d.get("tecnologias")),
        _bloque_tabla("superficies", d.get("superficies")),
        _bloque_tabla("cronograma", d.get("cronograma")),
        _bloque_tabla("modulos", d.get("modulos")),
        _bloque_tabla("adicionales", d.get("adicionales")),
        _bloque_tabla("sensores", d.get("sensores")),
    ])


def tarjeta_base_activa(token):
    if not D.usar(token):
        return None
    m = D.metadatos()
    return html.Section(className="tarjeta base-activa", children=[
        html.Div([html.Span("Base cargada", className="etiqueta-sol"),
                  html.H3(m.get("instalacion", "")),
                  html.P(f"Datos del {m.get('fecha_inicio')} al {m.get('fecha_fin')}. Solo tú la ves en esta "
                         f"pestaña del navegador; se borra a las {C.HORAS_CONSERVAR_CARGAS} horas.",
                         className="parrafo")]),
        html.Div(className="hero-botones", children=[
            dcc.Link("Ver mis datos", href="/energia", className="btn btn-pri"),
            html.Button("Volver a la plataforma de Sumicol", id={"type": "volver", "index": "datos"}, n_clicks=0,
                        className="btn btn-sec")]),
    ])


def pagina(token):
    activa = tarjeta_base_activa(token)
    D.usar(token)
    pasos = [
        ("1", "Crea tu plantilla", "Describe tu instalación en el formulario y descarga un archivo .db con las "
                                   "tablas listas y las columnas exactas de tus mediciones."),
        ("2", "Llena las mediciones", "Copia tus datos en las tablas de mediciones con Python, DB Browser for SQLite "
                                      "u otra herramienta. Fechas como AAAA-MM-DD HH:MM:SS."),
        ("3", "Carga tu base", "Súbela aquí: se revisa, se procesa y la ves en las pestañas de la plataforma."),
    ]
    return html.Div(className="contenedor pila", children=[
        activa,
        html.Div(className="rejilla-3", children=[
            html.Div(className="tarjeta paso", children=[
                html.Div(className="paso-tit", children=[html.Span(n, className="paso-num"), t]), html.P(txt)])
            for n, t, txt in pasos]),
        html.P([html.Button("Descargar la guía (PDF)", id="btn-guia", n_clicks=0, className="enlace-btn"),
                " · ",
                html.Button("Descargar la plantilla básica", id="btn-plantilla-vacia", n_clicks=0, className="enlace-btn")],
               className="nota"),

        html.Section(className="tarjeta tarjeta-grafica", children=[
            html.Div(className="tarjeta-cab explorar-cab", children=[
                html.Div([html.H3("1 · Crea tu plantilla"),
                          html.P("Los campos con * son obligatorios. Los códigos solo llevan letras sin tilde, "
                                 "números y _.")]),
                html.Button("Llenar con un ejemplo", id="btn-ejemplo", n_clicks=0, className="btn btn-sec btn-peq")]),
            html.Div(id="caja-formulario", children=formulario()),
            html.Div(className="form-acciones", children=[
                html.Button("Generar plantilla", id="btn-generar", n_clicks=0, className="btn btn-pri")]),
            html.Div(id="form-resultado"),
        ]),

        html.Section(className="tarjeta tarjeta-grafica", children=[
            html.Div(className="tarjeta-cab", children=[
                html.H3("3 · Carga tu base"),
                html.P(f"Base con el formato de la plantilla (hasta {C.MAX_MB_BASE_CARGA} MB) o, si es más grande, la base "
                       f"ya procesada en tu computador con procesamiento/procesar.py (hasta "
                       f"{C.MAX_MB_BASE_PROCESADA} MB).")]),
            dcc.Upload(id="carga-archivo", className="zona-carga", multiple=False,
                       max_size=C.MAX_MB_BASE_PROCESADA * 1024 * 1024 + 1, accept=".db,.sqlite,.sqlite3",
                       children=html.Div([html.Strong("Arrastra tu archivo .db aquí"), html.Br(),
                                          html.Span(f"o haz clic para elegirlo · máximo {C.MAX_MB_BASE_PROCESADA} MB "
                                                    "(los archivos más grandes no se envían)")])),
            dcc.Loading(type="dot", color="#1b554f", children=html.Div(id="carga-resultado")),
        ]),
    ])


# ------------------------------------------------------------------ acciones
def datos_formulario(nombre, descripcion, responsable, ciudad, pais, tec, sup, cron, mod, adic, sen):
    return {"instalacion": {"nombre": nombre, "descripcion": descripcion, "responsable": responsable,
                            "ciudad": ciudad, "pais": pais},
            "tecnologias": tec, "superficies": sup, "cronograma": cron, "modulos": mod, "adicionales": adic,
            "sensores": sen}


def lista_errores(titulo, errores, clase="aviso-errores"):
    return html.Div(className=f"tarjeta {clase}", children=[
        html.Strong(titulo), html.Ul([html.Li(e) for e in errores])])


def generar_plantilla(d):
    """(bytes del .db o None, componente con el resultado)."""
    C.CARPETA_CARGAS.mkdir(parents=True, exist_ok=True)
    ruta = C.CARPETA_CARGAS / f"plantilla_{uuid.uuid4().hex}.db"
    errores = PL.crear(d, ruta)
    if errores:
        return None, lista_errores("Revisa estos puntos antes de generar la plantilla:", errores)
    contenido = ruta.read_bytes()
    ruta.unlink(missing_ok=True)
    return contenido, html.Div(className="tarjeta aviso-ok", children=[
        html.Strong("Plantilla generada."),
        html.P("Llena las tablas mediciones_electricas y mediciones_ambientales (y energia_diaria si la tienes) "
               "y luego cárgala abajo.")])


def _limpiar_viejas():
    if not C.CARPETA_CARGAS.exists():
        return
    limite = time.time() - C.HORAS_CONSERVAR_CARGAS * 3600
    for f in C.CARPETA_CARGAS.glob("*.db"):
        try:
            if f.stat().st_mtime < limite:
                f.unlink()
        except OSError:
            pass


TABLAS_PROCESADA = {"metadatos", "superficies", "modulos", "iv_hora", "energia_dia", "irr_hora", "hsp_dia",
                    "meteo_hora", "temp_modulo_hora", "elec_hora", "amb_hora", "variables", "sensores"}


def _tipo_base(ruta):
    """'procesada', 'carga' o None si no es SQLite."""
    with open(ruta, "rb") as f:
        if f.read(16) != b"SQLite format 3\x00":
            return None
    con = sqlite3.connect(f"{ruta.resolve().as_uri()}?mode=ro", uri=True)
    try:
        tablas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if TABLAS_PROCESADA <= tablas:
            fmt = dict(con.execute("SELECT clave, valor FROM metadatos").fetchall()).get("formato")
            return "procesada" if fmt == "1.1" else "procesada_vieja"
        return "carga"
    finally:
        con.close()


def cargar(contenido, nombre):
    """Recibe el archivo del visitante. Devuelve (token o None, componente con el resultado)."""
    _limpiar_viejas()
    if not contenido:
        return None, None
    try:
        datos = base64.b64decode(contenido.split(",", 1)[1])
    except (IndexError, ValueError):
        return None, lista_errores("No se pudo leer el archivo.", ["Vuelve a intentarlo."])
    mb = len(datos) / 1024 / 1024
    C.CARPETA_CARGAS.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    subido = C.CARPETA_CARGAS / f"{token}_subido.db"
    destino = C.CARPETA_CARGAS / f"{token}.db"
    subido.write_bytes(datos)
    del datos
    try:
        tipo = _tipo_base(subido)
    except sqlite3.DatabaseError:
        tipo = None
    try:
        if tipo is None:
            return None, lista_errores(f"«{nombre}» no es una base SQLite.", ["Sube un archivo .db."])
        if tipo == "procesada_vieja":
            return None, lista_errores("Esta base procesada es de una versión anterior.",
                                       ["Vuelve a procesarla con procesamiento/procesar.py y súbela de nuevo."])
        if tipo == "procesada":
            if mb > C.MAX_MB_BASE_PROCESADA:
                return None, lista_errores("El archivo es demasiado grande.",
                                           [f"Pesa {mb:.0f} MB; el máximo es {C.MAX_MB_BASE_PROCESADA} MB."])
            shutil.move(subido, destino)
            return token, None
        # Base de carga: se valida y se procesa en un proceso aparte (así la memoria se libera al terminar)
        if mb > C.MAX_MB_BASE_CARGA:
            return None, lista_errores(
                "La base es demasiado grande para procesarla aquí.",
                [f"Pesa {mb:.0f} MB; el máximo para procesar en el servidor es {C.MAX_MB_BASE_CARGA} MB.",
                 "Procésala en tu computador con:  python procesamiento/procesar.py mi_base.db --destino mi_visor.db",
                 "y sube aquí el archivo mi_visor.db."])
        informe = Validador(subido).ejecutar()
        if informe.errores:
            hijos = [lista_errores(f"La base tiene {len(informe.errores)} error(es); corrígelos y vuelve a cargarla:",
                                   informe.errores)]
            if informe.avisos:
                hijos.append(lista_errores("Avisos:", informe.avisos, "aviso-avisos"))
            return None, html.Div(hijos)
        r = subprocess.run([sys.executable, str(C.RAIZ / "procesamiento" / "procesar.py"), str(subido),
                            "--destino", str(destino)], capture_output=True, text=True, timeout=600)
        if r.returncode != 0 or not destino.exists():
            detalle = (r.stdout + r.stderr).strip().splitlines()[-3:]
            return None, lista_errores("No se pudo procesar la base.", detalle or ["Error desconocido."])
        return token, None
    except subprocess.TimeoutExpired:
        return None, lista_errores("El procesamiento tardó demasiado.",
                                   ["Procésala en tu computador con procesamiento/procesar.py y sube el resultado."])
    finally:
        subido.unlink(missing_ok=True)
