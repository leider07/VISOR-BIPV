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
