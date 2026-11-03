"""
Genera la base liviana de la plataforma (data/visor.db) a partir de una base en formato de carga 1.1.

Uso (desde la carpeta del repositorio):
    python procesamiento/procesar.py ruta/a/mi_instalacion.db
    python procesamiento/procesar.py ruta/a/mi_instalacion.db --destino data/visor.db

Antes de procesar se valida la base (procesamiento/validar_bd.py); si tiene errores, se detiene.

La plataforma es un VISOR: no filtra ni descarta datos. Aquí solo se resume lo que trae la base
para que las páginas carguen rápido:
  - promedios por hora de potencia, irradiancia, temperaturas, humedad y viento
  - eficiencia por hora (con irradiancia >= 100 W/m²) y muestra para la dispersión potencia–irradiancia
  - horas de sol pico por día y superficie
  - energía diaria: la de la tabla energia_diaria si existe; si no, integrando la potencia
La base de carga solo se lee; nunca se modifica.
"""
import argparse
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import parametros as M  # noqa: E402
from validar_bd import Validador, imprimir  # noqa: E402

DESTINO = AQUI.parent / "data" / "visor.db"
FMT = "%Y-%m-%d %H:%M:%S"
# Tablas de información que se copian a la base de la plataforma
INFORMACION = ["instalacion", "tecnologias", "superficies", "modulos", "variables", "sensores",
               "cronograma_orientaciones"]


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def q(nombre):
    return '"' + nombre.replace('"', '""') + '"'


def con_fecha_hora(df):
    return df.assign(fecha=df.ts.dt.strftime("%Y-%m-%d"), hora=df.ts.dt.hour)


# --------------------------------------------------------------------------------------------
# Lectura
# --------------------------------------------------------------------------------------------
class Base:
    def __init__(self, ruta):
        self.con = sqlite3.connect(f"{Path(ruta).resolve().as_uri()}?mode=ro", uri=True)
        leer = lambda t: pd.read_sql(f"SELECT * FROM {q(t)}", self.con)
        tablas = {r[0] for r in self.con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.info = {t: leer(t) for t in INFORMACION if t in tablas}
        self.tiene_energia = "energia_diaria" in tablas and \
            self.con.execute("SELECT COUNT(*) FROM energia_diaria").fetchone()[0] > 0
        mod = self.info["modulos"].merge(self.info["tecnologias"], on="tecnologia_id", suffixes=("", "_tec"))
        self.modulos = mod.set_index("modulo_id")
        self.variables = self.info["variables"].set_index("variable_id")
        self.sensores = self.info["sensores"].set_index("sensor_id")

    def sensores_de(self, variable):
        return self.sensores[self.sensores.variable_id == variable]

    def ambientales(self, columnas):
        cols = ", ".join(["fecha_hora"] + [q(c) for c in columnas])
        m = pd.read_sql(f"SELECT {cols} FROM mediciones_ambientales", self.con)
        m["ts"] = pd.to_datetime(m.fecha_hora, format=FMT)
        m = m.drop(columns="fecha_hora")
        for c in columnas:
            m[c] = pd.to_numeric(m[c], errors="coerce")
        return m


# --------------------------------------------------------------------------------------------
# Resúmenes
# --------------------------------------------------------------------------------------------
def irradiancia_por_superficie(b):
    """Irradiancia por minuto de cada superficie (DataFrame ts, superficie, g)."""
    sens = b.sensores_de("irradiancia")
    if sens.empty:
        return pd.DataFrame(columns=["ts", "superficie", "g"])
    m = b.ambientales(list(sens.index))
    m["ts"] = m.ts.dt.floor("min")
    m = m.drop_duplicates("ts").rename(columns=sens.superficie_id.to_dict())
    return m.melt(id_vars="ts", var_name="superficie", value_name="g").dropna(subset=["g"])


def leer_electricas(b, irr):
    log("Leyendo mediciones eléctricas...")
    iv = pd.read_sql("SELECT fecha_hora, modulo_id, potencia_max_w FROM mediciones_electricas", b.con)
    iv["ts"] = pd.to_datetime(iv.fecha_hora, format=FMT).dt.floor("min")
    iv = iv.drop(columns="fecha_hora").rename(columns={"potencia_max_w": "p"})
    iv["p"] = pd.to_numeric(iv.p, errors="coerce")
    iv = iv.dropna(subset=["p"]).drop_duplicates(["modulo_id", "ts"])
    iv["superficie"] = iv.modulo_id.map(b.modulos.superficie_id)
    iv = con_fecha_hora(iv.merge(irr, on=["ts", "superficie"], how="left"))
    log(f"  {len(iv):,} mediciones; {int(iv.g.notna().sum()):,} con irradiancia de su superficie")
    return iv


def tablas_modulos(b, iv):
    area = iv.modulo_id.map(b.modulos.area_m2)
    alta = iv.g >= M.IRR_MIN_EFICIENCIA
    iv = iv.assign(p_ef=np.where(alta, iv.p, 0.0), ga_ef=np.where(alta, iv.g * area, 0.0))
    iv_hora = (iv.groupby(["modulo_id", "fecha", "hora"])
               .agg(g_media=("g", "mean"), p_media=("p", "mean"), n=("p", "size"),
                    p_ef=("p_ef", "sum"), ga_ef=("ga_ef", "sum")).reset_index())
    dias = iv.groupby(["modulo_id", "fecha"]).size().rename("registros").reset_index()

    con_g = iv.dropna(subset=["g"])
    disp = (con_g.set_index("ts").groupby("modulo_id")[["g", "p"]]
            .resample(f"{M.DISPERSION_MINUTOS}min").mean().dropna().reset_index())
    disp = disp[disp.g > M.DISPERSION_G_MIN]
    disp["ts"] = disp.ts.dt.strftime("%Y-%m-%d %H:%M")

    if b.tiene_energia:
        en = pd.read_sql("SELECT fecha, modulo_id, energia_wh FROM energia_diaria WHERE energia_wh IS NOT NULL", b.con)
        log("  Energía: tomada de la tabla energia_diaria")
    else:
        en = energia_integrada(iv)
        log("  Energía: calculada integrando la potencia (la base no trae energia_diaria)")
    en = en.groupby(["modulo_id", "fecha"], as_index=False).energia_wh.sum()
    log(f"  Energía: {len(en):,} días-módulo")
    return dias, iv_hora, disp, en


def energia_integrada(iv):
    """Energía por día y módulo integrando la potencia por el tiempo real entre lecturas."""
    d = iv.sort_values(["modulo_id", "ts"]).copy()
    dt = d.groupby(["modulo_id", "fecha"]).ts.diff().dt.total_seconds()
    d["wh"] = d.p * dt.fillna(60).clip(upper=M.DT_MAX_INTEGRACION) / 3600
    return d.groupby(["modulo_id", "fecha"]).wh.sum().rename("energia_wh").reset_index()


def tablas_irradiancia(irr):
    if irr.empty:
        return (pd.DataFrame(columns=["superficie", "fecha", "hora", "g_media", "minutos"]),
                pd.DataFrame(columns=["superficie", "fecha", "minutos", "hsp"]))
    irr = con_fecha_hora(irr)
    hora = (irr.groupby(["superficie", "fecha", "hora"])
            .agg(g_media=("g", "mean"), minutos=("g", "size")).reset_index())
    dia = hora.groupby(["superficie", "fecha"]).agg(wh=("g_media", "sum"), minutos=("minutos", "sum")).reset_index()
    dia["hsp"] = dia.wh / 1000.0
    log(f"  Irradiancia: {len(dia):,} días-superficie")
    return hora, dia.drop(columns="wh")


def tablas_meteo(b):
    log("Leyendo mediciones ambientales...")
    ta = list(b.sensores_de("temperatura_ambiente").index)
    vi = list(b.sensores_de("velocidad_viento").index)
    tm = b.sensores_de("temperatura_modulo")
    hr = list(b.sensores_de("humedad_relativa").index)
    cols = ta + vi + hr + list(tm.index)
    if not cols:
        return (pd.DataFrame(columns=["fecha", "hora", "ta_media", "viento_media", "hr_media"]),
                pd.DataFrame(columns=["fecha", "hora", "t_media", "modulo_id"]))
    m = con_fecha_hora(b.ambientales(cols))
    m["ta"] = m[ta].mean(axis=1) if ta else np.nan
    m["viento"] = m[vi].mean(axis=1) if vi else np.nan
    m["hr"] = m[hr].mean(axis=1) if hr else np.nan
    meteo = (m.groupby(["fecha", "hora"])
             .agg(ta_media=("ta", "mean"), viento_media=("viento", "mean"), hr_media=("hr", "mean"))
             .reset_index())
    filas = []
    for sid, r in tm.iterrows():
        t = m.groupby(["fecha", "hora"])[sid].mean().dropna().rename("t_media").reset_index()
        filas.append(t.assign(modulo_id=r.modulo_id))
    tmod = (pd.concat(filas, ignore_index=True) if filas
            else pd.DataFrame(columns=["fecha", "hora", "t_media", "modulo_id"]))
    log(f"  Ambientales: {len(meteo):,} horas; temperatura de {len(tm)} módulo(s)")
    return meteo, tmod


AGREGACION = {"promedio": "mean", "suma": "sum", "minimo": "min", "maximo": "max"}


def _resumen_horario(df, claves, columnas, variable_de, b):
    """Resume por hora cada columna con la agregación declarada para su variable."""
    df = con_fecha_hora(df)
    funcs = {}
    for c in columnas:
        v = variable_de(c)
        df[c] = pd.to_numeric(df[c], errors="coerce")
        funcs[c] = AGREGACION.get(b.variables.loc[v, "agregacion"], "mean")
    out = df.groupby(claves + ["fecha", "hora"]).agg(funcs).reset_index()
    return out.dropna(subset=columnas, how="all")


def tablas_explorar(b):
    """Resumen por hora de TODAS las variables (pestaña Explorar)."""
    cols_e = [r[1] for r in b.con.execute("PRAGMA table_info(mediciones_electricas)")]
    elec = [c for c in cols_e if c in b.variables.index and b.variables.loc[c, "tipo"] == "electrica"]
    e = pd.read_sql(f"SELECT fecha_hora, modulo_id, {', '.join(q(c) for c in elec)} FROM mediciones_electricas", b.con)
    e["ts"] = pd.to_datetime(e.fecha_hora, format=FMT)
    e = _resumen_horario(e.drop(columns="fecha_hora"), ["modulo_id"], elec, lambda c: c, b)
    sens = list(b.sensores.index)
    a = b.ambientales(sens) if sens else pd.DataFrame(columns=["ts"])
    a = _resumen_horario(a, [], sens, lambda c: b.sensores.loc[c, "variable_id"], b) if sens else a
    log(f"  Explorar: {len(elec)} variable(s) eléctrica(s) en {len(e):,} horas-módulo; "
        f"{len(sens)} sensor(es) en {len(a):,} horas")
    return e, a


def tabla_cronograma(b, fecha_fin):
    """Periodos de orientación por superficie (el último periodo abierto llega hasta el fin de los datos)."""
    cr = b.info.get("cronograma_orientaciones")
    if cr is None or cr.empty:
        return pd.DataFrame(columns=["superficie_id", "desde", "hasta", "orientacion"])
    cr = cr.copy()
    cr["desde"] = cr.desde.str[:10]
    cr["hasta"] = cr.hasta.fillna(fecha_fin + " 00:00:00").str[:10]
    return cr[["superficie_id", "desde", "hasta", "orientacion"]].sort_values(["superficie_id", "desde"])


def tablas_catalogo(b):
    """Superficies y módulos con el orden, las etiquetas y el color que usa el visor."""
    tec = b.info["tecnologias"].copy()
    tec["_t"] = tec.transmitancia_pct.fillna(1000)
    tec = tec.sort_values(["_t", "nombre"]).reset_index(drop=True)
    orden_tec = {t: i for i, t in enumerate(tec.tecnologia_id)}

    irr = set(b.sensores_de("irradiancia").superficie_id.dropna())
    sup = b.info["superficies"].copy().sort_values(["inclinacion_deg", "nombre"]).reset_index(drop=True)
    sup["orden"] = range(len(sup))
    sup["tiene_irradiancia"] = sup.superficie_id.isin(irr).astype(int)
    sup = sup[["superficie_id", "nombre", "inclinacion_deg", "orientacion", "orden", "tiene_irradiancia"]]

    con_temp = set(b.sensores_de("temperatura_modulo").modulo_id.dropna())
    mod = b.modulos.reset_index()
    mod["orden_tec"] = mod.tecnologia_id.map(orden_tec)
    mod["orden_sup"] = mod.superficie_id.map(dict(zip(sup.superficie_id, sup.orden)))
    mod = mod.sort_values(["orden_sup", "orden_tec", "modulo_id"]).reset_index(drop=True)
    base = mod.nombre.where(mod.nombre.notna() & (mod.nombre.astype(str).str.strip() != ""), mod.nombre_tec)
    repetido = mod.duplicated(["superficie_id", "tecnologia_id"], keep=False) & mod.nombre.isna()
    mod["etiqueta"] = np.where(repetido, base + " · " + mod.modulo_id, base)
    mod["color"] = mod.groupby("superficie_id").cumcount()      # posición dentro de su superficie
    mod["orden"] = range(len(mod))
    mod["tiene_temp"] = mod.modulo_id.isin(con_temp).astype(int)
    mod = mod.rename(columns={"nombre_tec": "tecnologia"})
    mod = mod[["modulo_id", "superficie_id", "tecnologia_id", "tecnologia", "etiqueta", "orden", "color",
               "area_m2", "potencia_stc_w", "transmitancia_pct", "tiene_temp"]]
    return sup, mod, tec.drop(columns="_t")


# --------------------------------------------------------------------------------------------
# Escritura: base de la plataforma
# --------------------------------------------------------------------------------------------
def escribir(tablas, destino):
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".tmp.db")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    for nombre, df in tablas.items():
        df.to_sql(nombre, con, index=False)
    idx = {"iv_hora": "fecha, modulo_id", "dispersion": "ts, modulo_id", "energia_dia": "fecha, modulo_id",
           "irr_hora": "fecha, superficie_id", "hsp_dia": "fecha, superficie_id", "meteo_hora": "fecha",
           "temp_modulo_hora": "fecha, modulo_id", "dias_modulo": "fecha, modulo_id",
           "elec_hora": "fecha, modulo_id", "amb_hora": "fecha"}
    for t, cols in idx.items():
        con.execute(f"CREATE INDEX ix_{t} ON {t} ({cols})")
    con.commit()
    con.execute("VACUUM")
    con.close()
    tmp.replace(destino)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("origen", type=Path, help="base en formato de carga 1.1")
    ap.add_argument("--destino", type=Path, default=DESTINO)
    a = ap.parse_args()
    t0 = time.time()

    log(f"Validando {a.origen} ...")
    r = Validador(a.origen).ejecutar()
    if r.errores:
        imprimir(r, a.origen)
        sys.exit(1)
    log(f"  Base válida ({len(r.avisos)} aviso(s))")

    b = Base(a.origen)
    irr = irradiancia_por_superficie(b)
    iv = leer_electricas(b, irr)
    log("Calculando tablas de módulos...")
    dias, iv_hora, disp, energia = tablas_modulos(b, iv)
    log("Calculando irradiancia y horas de sol pico por superficie...")
    irr_hora, hsp_dia = tablas_irradiancia(irr)
    meteo, tmod = tablas_meteo(b)
    log("Calculando promedios por hora para Explorar...")
    elec_hora, amb_hora = tablas_explorar(b)

    fechas = pd.concat([iv_hora.fecha, irr_hora.fecha, energia.fecha])
    horas = pd.concat([iv_hora.hora, irr_hora.hora, meteo.hora]).dropna()
    fecha_fin = fechas.max()
    crono = tabla_cronograma(b, fecha_fin)
    superficies, modulos, tecnologias = tablas_catalogo(b)
    b.con.close()

    inst = b.info["instalacion"].iloc[0]
    solo_vidrio = (tecnologias.tipo == "vidrio semitransparente").all()
    todas_caras = superficies.nombre.str.lower().str.startswith("cara").all()
    disponibles = [v for v in ["irradiancia", "temperatura_ambiente", "temperatura_modulo",
                               "humedad_relativa", "velocidad_viento"] if not b.sensores_de(v).empty]
    meta = {"fecha_inicio": fechas.min(), "fecha_fin": fecha_fin,
            "generado": datetime.now().strftime("%Y-%m-%d %H:%M"), "origen": a.origen.name, "formato": "1.1",
            "instalacion": inst.nombre, "descripcion": inst.get("descripcion"),
            "responsable": inst.get("responsable"), "ciudad": inst.get("ciudad"), "pais": inst.get("pais"),
            "modulo_palabra": "vidrio" if solo_vidrio else "módulo",
            "superficie_palabra": "cara" if todas_caras else "superficie",
            "variables": ",".join(disponibles),
            "hora_min": int(horas.min()), "hora_max": int(horas.max())}
    meta = {k: ("" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)) for k, v in meta.items()}
    tablas = {
        "superficies": superficies, "modulos": modulos, "tecnologias": tecnologias,
        "dias_modulo": dias, "iv_hora": iv_hora, "dispersion": disp, "energia_dia": energia,
        "irr_hora": irr_hora.rename(columns={"superficie": "superficie_id"}),
        "hsp_dia": hsp_dia.rename(columns={"superficie": "superficie_id"}),
        "meteo_hora": meteo, "temp_modulo_hora": tmod, "cronograma": crono,
        "elec_hora": elec_hora, "amb_hora": amb_hora,
        "variables": b.info["variables"], "sensores": b.info["sensores"],
        "metadatos": pd.DataFrame(list(meta.items()), columns=["clave", "valor"]),
    }
    log("Escribiendo base de la plataforma...")
    escribir(tablas, a.destino)
    log(f"Listo: {a.destino} ({a.destino.stat().st_size / 1e6:.1f} MB) · datos del "
        f"{meta['fecha_inicio']} al {meta['fecha_fin']} · {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
