"""Consultas a la base de la plataforma (data/visor.db)."""
import sqlite3
from functools import lru_cache

import pandas as pd

from . import config as C


def _q(sql, params=()):
    if not C.DB_VISOR.exists():
        raise FileNotFoundError(
            f"No existe {C.DB_VISOR}. Ejecuta primero:  python procesamiento/procesar.py mi_instalacion.db")
    con = sqlite3.connect(C.DB_VISOR.resolve().as_uri() + "?mode=ro", uri=True, check_same_thread=False)
    try:
        return pd.read_sql(sql, con, params=params)
    finally:
        con.close()


def _in(lista):
    return ",".join("?" * len(lista))


# ---------------------------- catálogo de la instalación ----------------------------
@lru_cache(maxsize=1)
def metadatos():
    df = _q("SELECT clave, valor FROM metadatos")
    return dict(zip(df.clave, df.valor))


@lru_cache(maxsize=1)
def superficies():
    return _q("SELECT * FROM superficies ORDER BY orden")


@lru_cache(maxsize=1)
def modulos():
    return _q("SELECT * FROM modulos ORDER BY orden")


@lru_cache(maxsize=1)
def cronograma():
    return _q("SELECT superficie_id, desde, hasta, orientacion FROM cronograma ORDER BY desde")


def variables():
    v = metadatos().get("variables", "")
    return set(v.split(",")) if v else set()


def es_resumen_fijo():
    return metadatos().get("instalacion") == C.INSTALACION_CON_RESUMEN


def modulos_de(superficie):
    m = modulos()
    return m[m.superficie_id == superficie]


def modulos_por_tecnologia(tecnologias, solo_con_temperatura=False):
    m = modulos()
    m = m[m.tecnologia_id.isin(tecnologias)]
    return m[m.tiene_temp == 1] if solo_con_temperatura else m


def tecnologias_de(ids):
    m = modulos()
    return list(dict.fromkeys(m[m.modulo_id.isin(ids)].tecnologia_id))


# ---------------------------- clima ----------------------------
def irr_hora(ini, fin):
    return _q("SELECT superficie_id, fecha, hora, g_media FROM irr_hora WHERE fecha BETWEEN ? AND ?", (ini, fin))


def matriz_irradiancia(ini, fin, superficie):
    """Tabla días x horas con la irradiancia promedio de cada hora (W/m²)."""
    df = _q("SELECT fecha, hora, g_media FROM irr_hora WHERE superficie_id = ? AND fecha BETWEEN ? AND ?",
            (superficie, ini, fin))
    if df.empty:
        return pd.DataFrame()
    return df.pivot_table(index="fecha", columns="hora", values="g_media", aggfunc="mean").sort_index()


def hsp_dia(ini, fin):
    return _q("SELECT superficie_id, fecha, hsp FROM hsp_dia WHERE valido = 1 AND fecha BETWEEN ? AND ? "
              "ORDER BY fecha", (ini, fin))


def meteo_hora(ini, fin):
    return _q("SELECT fecha, hora, ta_media, viento_media, hr_media FROM meteo_hora WHERE fecha BETWEEN ? AND ?",
              (ini, fin))


def temp_modulo_hora(ini, fin, ids):
    if not ids:
        return pd.DataFrame(columns=["modulo_id", "fecha", "hora", "t_media"])
    return _q(f"SELECT modulo_id, fecha, hora, t_media FROM temp_modulo_hora "
              f"WHERE fecha BETWEEN ? AND ? AND modulo_id IN ({_in(ids)})", (ini, fin, *ids))


# ---------------------------- módulos ----------------------------
def energia_dia(ini, fin, ids):
    if not ids:
        return pd.DataFrame(columns=["modulo_id", "fecha", "energia_wh"])
    return _q(f"SELECT modulo_id, fecha, energia_wh FROM energia_dia "
              f"WHERE fecha BETWEEN ? AND ? AND modulo_id IN ({_in(ids)}) ORDER BY fecha", (ini, fin, *ids))


def iv_hora(ini, fin, ids):
    if not ids:
        return pd.DataFrame(columns=["modulo_id", "fecha", "hora", "p_media", "p_ef", "ga_ef"])
    return _q(f"SELECT modulo_id, fecha, hora, p_media, p_ef, ga_ef FROM iv_hora "
              f"WHERE fecha BETWEEN ? AND ? AND modulo_id IN ({_in(ids)})", (ini, fin, *ids))


def dispersion(ini, fin, ids, max_por_modulo=4000):
    if not ids:
        return pd.DataFrame(columns=["modulo_id", "g", "p"])
    df = _q(f"SELECT modulo_id, g, p FROM dispersion "
            f"WHERE substr(ts, 1, 10) BETWEEN ? AND ? AND modulo_id IN ({_in(ids)})", (ini, fin, *ids))
    partes = [d.sample(min(len(d), max_por_modulo), random_state=1) for _, d in df.groupby("modulo_id")]
    return pd.concat(partes) if partes else df


# ---------------------------- explorar ----------------------------
@lru_cache(maxsize=1)
def variables_explorar():
    """Variables con datos: variable_id, nombre, unidad, tipo, es_fija (en el orden de la plataforma)."""
    v = _q("SELECT variable_id, nombre, unidad, tipo FROM variables")
    cols_e = set(_q("SELECT * FROM elec_hora LIMIT 0").columns)
    sens = sensores()
    v = v[((v.tipo == "electrica") & v.variable_id.isin(cols_e)) |
          ((v.tipo == "ambiental") & v.variable_id.isin(sens.variable_id))].copy()
    fijas = ["potencia_max_w", "voc_v", "isc_a", "vmpp_v", "impp_a", "irradiancia", "temperatura_ambiente",
             "temperatura_modulo", "humedad_relativa", "velocidad_viento"]
    v["es_fija"] = v.variable_id.isin(fijas)
    v["orden"] = [(0 if t == "electrica" else 1, fijas.index(i) if i in fijas else 99, i)
                  for t, i in zip(v.tipo, v.variable_id)]
    return v.sort_values("orden").drop(columns="orden").set_index("variable_id")


@lru_cache(maxsize=1)
def sensores():
    return _q("SELECT sensor_id, variable_id, superficie_id, modulo_id FROM sensores")


def _nombre_sup(sid):
    s = superficies()
    return s[s.superficie_id == sid].nombre.iloc[0]


def entidades(variable):
    """Dónde se midió una variable: lista de (id, etiqueta) de módulos o sensores, en orden."""
    v = variables_explorar()
    if variable not in v.index:
        return []
    varias_sup = superficies().superficie_id.nunique() > 1
    if v.loc[variable, "tipo"] == "electrica":
        return [(r.modulo_id, f"{_nombre_sup(r.superficie_id)} · {r.etiqueta}" if varias_sup else r.etiqueta)
                for r in modulos().itertuples()]
    s = sensores()
    s = s[s.variable_id == variable].copy()
    m = modulos().set_index("modulo_id")
    so = dict(zip(superficies().superficie_id, superficies().orden))
    s["_o"] = [(m.loc[mo, "orden"] if isinstance(mo, str) else so.get(su, -1) * 100) for mo, su in
               zip(s.modulo_id, s.superficie_id)]
    out = []
    for r in s.sort_values("_o").itertuples():
        if isinstance(r.modulo_id, str):
            mod = m.loc[r.modulo_id]
            et = f"{_nombre_sup(mod.superficie_id)} · {mod.etiqueta}" if varias_sup else mod.etiqueta
        elif isinstance(r.superficie_id, str):
            et = _nombre_sup(r.superficie_id)
        else:
            et = "Sitio"
        out.append((r.sensor_id, et))
    vistos = [e for _, e in out]
    return [(i, f"{e} · {i}" if vistos.count(e) > 1 else e) for i, e in out]


def superficie_de(entidad):
    """Superficie (y módulo) de un módulo o sensor, para emparejar variables."""
    m = modulos().set_index("modulo_id")
    if entidad in m.index:
        return m.loc[entidad, "superficie_id"], entidad
    s = sensores().set_index("sensor_id")
    if entidad in s.index:
        r = s.loc[entidad]
        if isinstance(r.modulo_id, str):
            return m.loc[r.modulo_id, "superficie_id"], r.modulo_id
        return (r.superficie_id if isinstance(r.superficie_id, str) else None), None
    return None, None


def pareja(variable, entidad):
    """Módulo o sensor de `variable` que corresponde a `entidad` (mismo módulo, misma superficie o sitio)."""
    v = variables_explorar()
    sup, mod = superficie_de(entidad)
    if v.loc[variable, "tipo"] == "electrica":
        return mod
    s = sensores()
    s = s[s.variable_id == variable]
    for cond in [s.modulo_id == mod, s.superficie_id == sup, s.modulo_id.isna() & s.superficie_id.isna()]:
        c = s[cond.fillna(False)]
        if len(c):
            return c.sensor_id.iloc[0]
    return s.sensor_id.iloc[0] if len(s) else None


def serie(variable, entidad, ini, fin):
    """Valores por hora (fecha, hora, valor) de una variable en un módulo o sensor."""
    if variable not in variables_explorar().index or entidad is None:
        return pd.DataFrame(columns=["fecha", "hora", "valor"])
    if variables_explorar().loc[variable, "tipo"] == "electrica":
        if entidad not in set(modulos().modulo_id):
            return pd.DataFrame(columns=["fecha", "hora", "valor"])
        col = '"' + variable.replace('"', '""') + '"'
        df = _q(f"SELECT fecha, hora, {col} AS valor FROM elec_hora WHERE modulo_id = ? AND fecha BETWEEN ? AND ?",
                (entidad, ini, fin))
    else:
        if entidad not in set(sensores().sensor_id):
            return pd.DataFrame(columns=["fecha", "hora", "valor"])
        col = '"' + entidad.replace('"', '""') + '"'
        df = _q(f"SELECT fecha, hora, {col} AS valor FROM amb_hora WHERE fecha BETWEEN ? AND ?", (ini, fin))
    return df.dropna(subset=["valor"])
