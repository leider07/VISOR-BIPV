"""
Genera la base liviana de la plataforma (data/visor.db) a partir de una base en formato de carga 1.1.

Uso (desde la carpeta Visor_BIPV):
    python procesamiento/procesar.py ruta/a/mi_instalacion.db
    python procesamiento/procesar.py ruta/a/mi_instalacion.db --destino data/visor.db

Antes de procesar se valida la base (procesamiento/validar_bd.py); si tiene errores, se detiene.

Pasos (metodología en procesamiento/metodologia.py):
  - ventana horaria
  - irradiancia de cada módulo: la del sensor de su superficie en el mismo minuto
  - filtro híbrido por módulo (límites frente a la potencia STC + tubo estadístico)
  - días válidos por número de mediciones limpias
  - eficiencia, horas de sol pico, temperaturas y viento por hora
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
import metodologia as M  # noqa: E402
from validar_bd import Validador, imprimir  # noqa: E402

DESTINO = AQUI.parent / "data" / "visor.db"
FMT = "%Y-%m-%d %H:%M:%S"
# Tablas de información que se copian tal cual a la base de la plataforma
INFORMACION = ["instalacion", "tecnologias", "superficies", "modulos", "variables", "sensores",
               "cronograma_orientaciones"]


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def q(nombre):
    return '"' + nombre.replace('"', '""') + '"'


def en_ventana(ts):
    return (ts.dt.hour >= M.HORA_INICIO) & (ts.dt.hour < M.HORA_FIN)


def dentro(s, mn, mx):
    """Deja en NaN los valores fuera de [mn, mx] (límites vacíos = sin límite)."""
    ok = pd.Series(True, index=s.index)
    if mn is not None and not pd.isna(mn):
        ok &= s >= mn
    if mx is not None and not pd.isna(mx):
        ok &= s <= mx
    return s.where(ok)


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

    def limites(self, variable):
        if variable not in self.variables.index:
            return None, None
        r = self.variables.loc[variable]
        return r.min_valido, r.max_valido

    def sensores_de(self, variable):
        return self.sensores[self.sensores.variable_id == variable]

    def ambientales(self, columnas):
        cols = ", ".join(["fecha_hora"] + [q(c) for c in columnas])
        m = pd.read_sql(f"SELECT {cols} FROM mediciones_ambientales", self.con)
        m["ts"] = pd.to_datetime(m.fecha_hora, format=FMT)
        m = m.drop(columns="fecha_hora")
        for c in columnas:
            v = self.sensores.loc[c, "variable_id"]
            m[c] = dentro(pd.to_numeric(m[c], errors="coerce"), *self.limites(v))
        return m


# --------------------------------------------------------------------------------------------
# Filtro híbrido (misma metodología de los notebooks de análisis)
# --------------------------------------------------------------------------------------------
def ghost_pct(transmitancia):
    if transmitancia is None or pd.isna(transmitancia):
        return M.GHOST_PCT
    return M.GHOST_PCT_POR_TRANSMITANCIA.get(int(round(transmitancia)), M.GHOST_PCT)


def filtrar_modulo(df, stc, area, ghost):
    m = (df.g > M.IRR_MIN) & (df.g < M.IRR_MAX) & (df.p > stc * M.MIN_P_PCT)
    d = df[m]
    fantasma = (d.p > stc * ghost) & (d.g < M.IRR_LOGICA)
    muerto = (d.p < stc * M.MIN_P_PCT) & (d.g > M.IRR_LOGICA)
    d = d[~fantasma & ~muerto].copy()
    if d.empty:
        return d
    d["pn"] = d.p / area
    d["bin"] = (d.g // M.TUBO_BIN) * M.TUBO_BIN
    st = d.groupby("bin")["pn"].quantile([M.TUBO_Q_BAJO, M.TUBO_Q_ALTO]).unstack().sort_index()
    st.columns = ["q_bajo", "q_alto"]
    lo = st.q_bajo.rolling(M.TUBO_VENTANA, center=True, min_periods=1).mean()
    hi = st.q_alto.rolling(M.TUBO_VENTANA, center=True, min_periods=1).mean()
    margen = np.maximum((hi - lo) * M.TUBO_EXPANSION, M.TUBO_MARGEN_MIN)
    d = d.join(pd.DataFrame({"inf": lo - margen, "sup": hi + margen}), on="bin")
    return d[(d.pn >= d.inf) & (d.pn <= d.sup)].drop(columns=["pn", "bin", "inf", "sup"])


# --------------------------------------------------------------------------------------------
# Pasos
# --------------------------------------------------------------------------------------------
def irradiancia_por_superficie(b):
    """Irradiancia por minuto de cada superficie (DataFrame ts, superficie, g)."""
    sens = b.sensores_de("irradiancia")
    if sens.empty:
        return pd.DataFrame(columns=["ts", "superficie", "g"])
    m = b.ambientales(list(sens.index))
    m["ts"] = m.ts.dt.floor("min")
    m = m.drop_duplicates("ts")
    m = m[en_ventana(m.ts)]
    m = m.rename(columns=sens.superficie_id.to_dict())
    return m.melt(id_vars="ts", var_name="superficie", value_name="g").dropna(subset=["g"])


def procesar_electricas(b, irr):
    log("Leyendo mediciones eléctricas...")
    iv = pd.read_sql("SELECT fecha_hora, modulo_id, potencia_max_w FROM mediciones_electricas", b.con)
    iv["ts"] = pd.to_datetime(iv.fecha_hora, format=FMT).dt.floor("min")
    iv = iv[en_ventana(iv.ts)].drop(columns="fecha_hora").rename(columns={"potencia_max_w": "p"})
    iv["p"] = dentro(iv.p, *b.limites("potencia_max_w"))
    iv = iv.drop_duplicates(["modulo_id", "ts"])
    iv["superficie"] = iv.modulo_id.map(b.modulos.superficie_id)
    iv = iv.merge(irr, on=["ts", "superficie"], how="left")
    log(f"  {len(iv):,} mediciones dentro de la ventana horaria; "
        f"{int(iv.g.notna().sum()):,} con irradiancia de su superficie")

    log("Aplicando filtro híbrido por módulo...")
    partes = []
    for mid, d in iv.dropna(subset=["g", "p"]).groupby("modulo_id"):
        r = b.modulos.loc[mid]
        f = filtrar_modulo(d, r.potencia_stc_w, r.area_m2, ghost_pct(r.transmitancia_pct))
        partes.append(f)
        log(f"  {mid}: {len(d):,} -> {len(f):,} mediciones limpias")
    # Superficies sin ningún sensor de irradiancia: solo límites físicos de potencia (sin filtro híbrido)
    sin_sensor = set(b.info["superficies"].superficie_id) - set(b.sensores_de("irradiancia").superficie_id.dropna())
    for mid, d in iv[iv.superficie.isin(sin_sensor)].dropna(subset=["p"]).groupby("modulo_id"):
        stc = b.modulos.loc[mid].potencia_stc_w
        f = d[(d.p >= 0) & (d.p <= stc * M.P_MAX_SIN_IRR)]
        partes.append(f)
        log(f"  {mid}: {len(d):,} -> {len(f):,} mediciones (superficie sin irradiancia: solo límites de potencia)")
    limpio = pd.concat(partes, ignore_index=True) if partes else iv.iloc[:0]
    # Días-módulo sin ninguna irradiancia (p. ej. periodo sin sensor): se validan solo por número de lecturas
    iv["fecha"] = iv.ts.dt.strftime("%Y-%m-%d")
    sin_irr = iv.groupby(["modulo_id", "fecha"]).g.apply(lambda s: s.isna().all())
    sin_irr = sin_irr[sin_irr].reset_index()[["modulo_id", "fecha"]]
    return iv, limpio, sin_irr


def tablas_modulos(b, iv, limpio, sin_irr):
    limpio = limpio.copy()
    limpio["fecha"] = limpio.ts.dt.strftime("%Y-%m-%d")
    limpio["hora"] = limpio.ts.dt.hour
    area = limpio.modulo_id.map(b.modulos.area_m2)

    cuenta = limpio.groupby(["modulo_id", "fecha"]).size().rename("registros").reset_index()
    cuenta["valido"] = (cuenta.registros >= M.UMBRAL_REGISTROS_DIA).astype(int)

    alta = limpio.g >= M.IRR_MIN_EFICIENCIA
    limpio["p_ef"] = np.where(alta, limpio.p, 0.0)
    limpio["ga_ef"] = np.where(alta, limpio.g * area, 0.0)
    iv_hora = (limpio.groupby(["modulo_id", "fecha", "hora"])
               .agg(g_media=("g", "mean"), p_media=("p", "mean"), n=("p", "size"),
                    p_ef=("p_ef", "sum"), ga_ef=("ga_ef", "sum")).reset_index())

    disp = (limpio.set_index("ts").groupby("modulo_id")[["g", "p"]]
            .resample(f"{M.DISPERSION_MINUTOS}min").mean().dropna().reset_index())
    disp = disp[disp.g > M.DISPERSION_G_MIN]
    disp["ts"] = disp.ts.dt.strftime("%Y-%m-%d %H:%M")

    # Energía diaria
    if b.tiene_energia:
        en = pd.read_sql("SELECT fecha, modulo_id, energia_wh, data_points FROM energia_diaria "
                         "WHERE energia_wh IS NOT NULL", b.con)
        log("  Energía: tomada de la tabla energia_diaria")
    else:
        en = energia_integrada(iv)
        log("  Energía: calculada integrando la potencia (no hay tabla energia_diaria)")
    validos = cuenta[cuenta.valido == 1][["modulo_id", "fecha"]]
    lecturas = en[en.data_points.fillna(0) >= M.UMBRAL_REGISTROS_DIA][["modulo_id", "fecha"]]
    sin = sin_irr.merge(lecturas, on=["modulo_id", "fecha"])
    if len(sin):
        log(f"  Energía: {len(sin):,} días-módulo sin irradiancia validados por número de mediciones")
    validos = pd.concat([validos, sin]).drop_duplicates()
    en = en.merge(validos, on=["modulo_id", "fecha"]).drop(columns="data_points")
    en = en.groupby(["modulo_id", "fecha"], as_index=False).energia_wh.sum()
    log(f"  Energía: {len(en):,} días-módulo válidos")
    return cuenta, iv_hora, disp, en


def energia_integrada(iv):
    """Energía por día y módulo integrando la potencia por el tiempo real entre lecturas (máx. 15 min)."""
    d = iv.dropna(subset=["p"]).sort_values(["modulo_id", "ts"]).copy()
    dt = d.groupby(["modulo_id", "fecha"]).ts.diff().dt.total_seconds()
    d["dt"] = dt.fillna(60).clip(upper=900)
    d["wh"] = d.p.clip(lower=0) * d.dt / 3600
    return (d.groupby(["modulo_id", "fecha"])
            .agg(energia_wh=("wh", "sum"), data_points=("p", "size")).reset_index())


def tablas_irradiancia(irr):
    if irr.empty:
        return (pd.DataFrame(columns=["superficie", "fecha", "hora", "g_media", "minutos"]),
                pd.DataFrame(columns=["superficie", "fecha", "minutos", "hsp", "valido"]))
    irr = irr.assign(fecha=irr.ts.dt.strftime("%Y-%m-%d"), hora=irr.ts.dt.hour)
    hora = (irr.groupby(["superficie", "fecha", "hora"])
            .agg(g_media=("g", "mean"), minutos=("g", "size")).reset_index())
    dia = hora.groupby(["superficie", "fecha"]).agg(wh=("g_media", "sum"), minutos=("minutos", "sum")).reset_index()
    dia["hsp"] = dia.wh / 1000.0
    esperados = M.MINUTOS_ESPERADOS_DIA
    dia["valido"] = (dia.minutos >= M.FRACCION_MIN_DIA_IRR * esperados).astype(int)
    dia = dia.drop(columns="wh")
    hora = hora.merge(dia[dia.valido == 1][["superficie", "fecha"]], on=["superficie", "fecha"])
    log(f"  Irradiancia: {int(dia.valido.sum()):,} días-superficie válidos de {len(dia):,}")
    return hora, dia


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
    m = b.ambientales(cols)
    m = m[en_ventana(m.ts)]
    m["fecha"] = m.ts.dt.strftime("%Y-%m-%d")
    m["hora"] = m.ts.dt.hour

    def temp_ok(s):
        return s.where((s >= M.TEMP_MIN) & (s <= M.TEMP_MAX))

    m["ta"] = temp_ok(m[ta].mean(axis=1)) if ta else np.nan
    m["viento"] = m[vi].where(m[vi] > M.VIENTO_MIN_EXCLUSIVO).mean(axis=1) if vi else np.nan
    m["hr"] = m[hr].mean(axis=1) if hr else np.nan
    meteo = (m.groupby(["fecha", "hora"])
             .agg(ta_media=("ta", "mean"), viento_media=("viento", "mean"), hr_media=("hr", "mean"))
             .reset_index())
    filas = []
    for sid, r in tm.iterrows():
        t = m[["fecha", "hora"]].assign(t=temp_ok(m[sid]))
        t = t.groupby(["fecha", "hora"]).t.mean().dropna().reset_index()
        t["modulo_id"] = r.modulo_id
        filas.append(t.rename(columns={"t": "t_media"}))
    tmod = (pd.concat(filas, ignore_index=True) if filas
            else pd.DataFrame(columns=["fecha", "hora", "t_media", "modulo_id"]))
    log(f"  Ambientales: {len(meteo):,} horas; temperatura de {len(tm)} módulo(s)")
    return meteo, tmod


AGREGACION = {"promedio": "mean", "suma": "sum", "minimo": "min", "maximo": "max"}


def _resumen_horario(df, claves, columnas, variable_de, b):
    """Resume por hora cada columna con la agregación y los límites de su variable."""
    df = df[en_ventana(df.ts)].copy()
    df["fecha"] = df.ts.dt.strftime("%Y-%m-%d")
    df["hora"] = df.ts.dt.hour
    funcs = {}
    for c in columnas:
        v = variable_de(c)
        df[c] = dentro(pd.to_numeric(df[c], errors="coerce"), *b.limites(v))
        funcs[c] = AGREGACION.get(b.variables.loc[v, "agregacion"], "mean")
    out = df.groupby(claves + ["fecha", "hora"]).agg(funcs).reset_index()
    return out.dropna(subset=columnas, how="all")


def tablas_explorar(b):
    """Promedios por hora de TODAS las variables, sin filtro híbrido (solo límites de cada variable)."""
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
# Escritura: mismo esquema que lee el visor actual + las tablas de información
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
    iv, limpio, sin_irr = procesar_electricas(b, irr)
    log("Calculando tablas de módulos...")
    dias, iv_hora, disp, energia = tablas_modulos(b, iv, limpio, sin_irr)
    log("Calculando irradiancia y horas de sol pico por superficie...")
    irr_hora, hsp_dia = tablas_irradiancia(irr)
    meteo, tmod = tablas_meteo(b)
    log("Calculando promedios por hora para Explorar...")
    elec_hora, amb_hora = tablas_explorar(b)

    fechas = pd.concat([iv_hora.fecha, irr_hora.fecha, energia.fecha])
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
            "variables": ",".join(disponibles)}
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
