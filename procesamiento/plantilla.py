"""
Plantillas del formato de carga.

- crear(): la usa el formulario de la pestaña «Tus datos». Con lo que se llena allí se crea un .db con
  las tablas de información ya escritas y las tablas de mediciones vacías, con exactamente las
  columnas declaradas (una por variable eléctrica y una por sensor).
- basica(): la plantilla básica (formato/plantilla.db), con solo las columnas obligatorias:
      python procesamiento/plantilla.py formato/plantilla.db
"""
import re
import sqlite3
from pathlib import Path

AQUI = Path(__file__).resolve().parent
ESQUEMA = AQUI.parent / "formato" / "esquema.sql"

TIPOS_TECNOLOGIA = ["c-Si mono", "c-Si poli", "CdTe", "CIGS", "a-Si", "perovskita", "vidrio semitransparente", "otro"]
ORIENTACIONES = ["Norte", "Noreste", "Este", "Sureste", "Sur", "Suroeste", "Oeste", "Noroeste"]
AGREGACIONES = ["promedio", "suma", "minimo", "maximo"]
ELECTRICAS_OPCIONALES = ["voc_v", "isc_a", "vmpp_v", "impp_a"]
AMBIENTALES_FIJAS = ["irradiancia", "temperatura_ambiente", "temperatura_modulo", "humedad_relativa",
                     "velocidad_viento"]
CODIGO = re.compile(r"^[A-Za-z0-9_]+$")
FECHA_HORA = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def fecha_hora(v):
    """Acepta AAAA-MM-DD HH:MM:SS o AAAA-MM-DD (se completa con 00:00:00). None si está vacía o mal escrita."""
    t = _txt(v)
    if FECHA.match(t):
        t += " 00:00:00"
    return t if FECHA_HORA.match(t) else None


def _txt(v):
    return "" if v is None else str(v).strip()


def _num(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _filas(lista):
    """Quita filas totalmente vacías de una tabla del formulario."""
    return [f for f in (lista or []) if any(_txt(v) for v in f.values())]


def revisar(d):
    """Revisa la descripción del formulario y devuelve una lista de errores en lenguaje claro."""
    e = []
    inst = d.get("instalacion", {})
    if not _txt(inst.get("nombre")):
        e.append("Instalación: falta el nombre.")

    def codigos(tabla, filas, col, que):
        vistos = set()
        for i, f in enumerate(filas, 1):
            c = _txt(f.get(col))
            if not c:
                e.append(f"{tabla}, fila {i}: falta el código ({col}).")
            elif not CODIGO.match(c):
                e.append(f"{tabla}, fila {i}: el código «{c}» solo puede tener letras sin tilde, números y _.")
            elif c in vistos:
                e.append(f"{tabla}: el código «{c}» está repetido.")
            vistos.add(c)
        if not filas:
            e.append(f"{tabla}: agrega al menos {que}.")
        return vistos

    tec = _filas(d.get("tecnologias"))
    ids_tec = codigos("Tecnologías", tec, "tecnologia_id", "una tecnología")
    for i, f in enumerate(tec, 1):
        if not _txt(f.get("nombre")):
            e.append(f"Tecnologías, fila {i}: falta el nombre.")
        if _txt(f.get("tipo")) not in TIPOS_TECNOLOGIA:
            e.append(f"Tecnologías, fila {i}: elige el tipo de la lista.")
        for col, que in [("potencia_stc_w", "la potencia STC"), ("area_m2", "el área")]:
            v = _num(f.get(col))
            if v is None or v <= 0:
                e.append(f"Tecnologías, fila {i}: {que} debe ser un número mayor que 0.")
        t = f.get("transmitancia_pct")
        if _txt(t) and (_num(t) is None or not 0 <= _num(t) <= 100):
            e.append(f"Tecnologías, fila {i}: la transmitancia debe estar entre 0 y 100.")

    sup = _filas(d.get("superficies"))
    ids_sup = codigos("Superficies", sup, "superficie_id", "una superficie")
    for i, f in enumerate(sup, 1):
        if not _txt(f.get("nombre")):
            e.append(f"Superficies, fila {i}: falta el nombre.")
        v = _num(f.get("inclinacion_deg"))
        if v is None or not 0 <= v <= 90:
            e.append(f"Superficies, fila {i}: la inclinación debe ser un número entre 0 y 90.")
        o = _txt(f.get("orientacion"))
        if o and o not in ORIENTACIONES:
            e.append(f"Superficies, fila {i}: elige la orientación de la lista.")

    cron = _filas(d.get("cronograma"))
    periodos = {}
    for i, f in enumerate(cron, 1):
        s = _txt(f.get("superficie_id"))
        if s not in ids_sup:
            e.append(f"Cronograma, fila {i}: elige una superficie de la tabla Superficies.")
        ini, fin = fecha_hora(f.get("desde")), fecha_hora(f.get("hasta"))
        if not ini:
            e.append(f"Cronograma, fila {i}: «Desde» debe escribirse AAAA-MM-DD o AAAA-MM-DD HH:MM:SS.")
        if _txt(f.get("hasta")) and not fin:
            e.append(f"Cronograma, fila {i}: «Hasta» debe escribirse AAAA-MM-DD o AAAA-MM-DD HH:MM:SS.")
        if ini and fin and fin <= ini:
            e.append(f"Cronograma, fila {i}: «Hasta» debe ser posterior a «Desde».")
        if _txt(f.get("orientacion")) not in ORIENTACIONES:
            e.append(f"Cronograma, fila {i}: elige la orientación de la lista.")
        incl = f.get("inclinacion_deg")
        if _txt(incl) and (_num(incl) is None or not 0 <= _num(incl) <= 90):
            e.append(f"Cronograma, fila {i}: la inclinación debe ser un número entre 0 y 90.")
        if s and ini:
            periodos.setdefault(s, []).append((ini, fin))
    for s, ps in periodos.items():
        ps.sort()
        for (a1, b1), (a2, _b2) in zip(ps, ps[1:]):
            if b1 is None or a2 < b1:
                e.append(f"Cronograma: en «{s}» hay periodos que se cruzan (el que empieza {a1} y el que empieza {a2}).")

    mod = _filas(d.get("modulos"))
    ids_mod = codigos("Módulos", mod, "modulo_id", "un módulo")
    for i, f in enumerate(mod, 1):
        if _txt(f.get("superficie_id")) not in ids_sup:
            e.append(f"Módulos, fila {i}: elige una superficie de la tabla Superficies.")
        if _txt(f.get("tecnologia_id")) not in ids_tec:
            e.append(f"Módulos, fila {i}: elige una tecnología de la tabla Tecnologías.")

    adic = _filas(d.get("adicionales"))
    reservados = set(AMBIENTALES_FIJAS + ["potencia_max_w", "fecha_hora", "modulo_id"])
    ids_adic = set()
    for i, f in enumerate(adic, 1):
        c = _txt(f.get("variable_id"))
        if not c or not CODIGO.match(c):
            e.append(f"Otras variables, fila {i}: el código solo puede tener letras sin tilde, números y _.")
        elif c in reservados or c in ids_adic:
            e.append(f"Otras variables, fila {i}: el código «{c}» ya existe.")
        ids_adic.add(c)
        if not _txt(f.get("nombre")):
            e.append(f"Otras variables, fila {i}: falta el nombre.")
        if _txt(f.get("tipo")) not in ("electrica", "ambiental"):
            e.append(f"Otras variables, fila {i}: elige si es eléctrica o ambiental.")
        elif c in ELECTRICAS_OPCIONALES and _txt(f.get("tipo")) != "electrica":
            e.append(f"Otras variables, fila {i}: «{c}» es una variable eléctrica.")
        if _txt(f.get("agregacion")) and _txt(f.get("agregacion")) not in AGREGACIONES:
            e.append(f"Otras variables, fila {i}: elige cómo se resume (promedio, suma, mínimo o máximo).")
    amb_adic = {_txt(f.get("variable_id")) for f in adic if _txt(f.get("tipo")) == "ambiental"}

    sen = _filas(d.get("sensores"))
    vistos = set()
    for i, f in enumerate(sen, 1):
        c = _txt(f.get("sensor_id"))
        v = _txt(f.get("variable_id"))
        if not c or not CODIGO.match(c):
            e.append(f"Sensores, fila {i}: el nombre de la columna solo puede tener letras sin tilde, números y _.")
        elif c in vistos or c in ids_mod or c == "fecha_hora":
            e.append(f"Sensores, fila {i}: la columna «{c}» está repetida.")
        vistos.add(c)
        if v not in AMBIENTALES_FIJAS and v not in amb_adic:
            e.append(f"Sensores, fila {i}: elige qué mide el sensor.")
        s, m = _txt(f.get("superficie_id")), _txt(f.get("modulo_id"))
        if s and s not in ids_sup:
            e.append(f"Sensores, fila {i}: la superficie «{s}» no está en la tabla Superficies.")
        if m and m not in ids_mod:
            e.append(f"Sensores, fila {i}: el módulo «{m}» no está en la tabla Módulos.")
        if v == "irradiancia" and not s:
            e.append(f"Sensores, fila {i}: un sensor de irradiancia necesita su superficie.")
        if v == "temperatura_modulo" and not m:
            e.append(f"Sensores, fila {i}: un sensor de temperatura de módulo necesita su módulo.")
        if s and m:
            e.append(f"Sensores, fila {i}: elige superficie o módulo, no los dos.")
    irr = [_txt(f.get("superficie_id")) for f in sen if _txt(f.get("variable_id")) == "irradiancia"]
    for s in sorted({x for x in irr if irr.count(x) > 1}):
        e.append(f"Sensores: la superficie «{s}» tiene más de un sensor de irradiancia; debe tener uno solo.")
    return e


def crear(d, destino):
    """Crea la plantilla en `destino`. Devuelve la lista de errores (vacía si todo salió bien)."""
    errores = revisar(d)
    if errores:
        return errores
    destino = Path(destino)
    destino.unlink(missing_ok=True)
    con = sqlite3.connect(destino)
    try:
        con.executescript(ESQUEMA.read_text(encoding="utf-8"))
        con.execute("PRAGMA foreign_keys = ON")
        inst = d.get("instalacion", {})
        con.execute("INSERT INTO instalacion (nombre, descripcion, responsable, ciudad, pais) "
                    "VALUES (?, ?, ?, ?, ?)",
                    [_txt(inst.get(k)) or None for k in ["nombre", "descripcion", "responsable", "ciudad", "pais"]])
        for f in _filas(d.get("tecnologias")):
            con.execute("INSERT INTO tecnologias (tecnologia_id, nombre, tipo, potencia_stc_w, area_m2, "
                        "transmitancia_pct, fabricante, modelo) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        [_txt(f["tecnologia_id"]), _txt(f["nombre"]), _txt(f["tipo"]), _num(f["potencia_stc_w"]),
                         _num(f["area_m2"]), _num(f.get("transmitancia_pct")) if _txt(f.get("transmitancia_pct")) else None,
                         _txt(f.get("fabricante")) or None, _txt(f.get("modelo")) or None])
        for f in _filas(d.get("superficies")):
            con.execute("INSERT INTO superficies VALUES (?, ?, ?, ?, ?)",
                        [_txt(f["superficie_id"]), _txt(f["nombre"]), _num(f["inclinacion_deg"]),
                         _txt(f.get("orientacion")) or None, _txt(f.get("descripcion")) or None])
        for f in _filas(d.get("cronograma")):
            con.execute("INSERT INTO cronograma_orientaciones VALUES (?, ?, ?, ?, ?)",
                        [_txt(f["superficie_id"]), fecha_hora(f["desde"]), fecha_hora(f.get("hasta")),
                         _txt(f["orientacion"]),
                         _num(f.get("inclinacion_deg")) if _txt(f.get("inclinacion_deg")) else None])
        for f in _filas(d.get("modulos")):
            con.execute("INSERT INTO modulos VALUES (?, ?, ?, ?)",
                        [_txt(f["modulo_id"]), _txt(f["superficie_id"]), _txt(f["tecnologia_id"]),
                         _txt(f.get("nombre")) or None])

        # Variables: se dejan solo las que se van a entregar
        sen = _filas(d.get("sensores"))
        usadas_amb = {_txt(f["variable_id"]) for f in sen}
        adic = _filas(d.get("adicionales"))
        electricas = {_txt(f["variable_id"]) for f in adic if _txt(f.get("tipo")) == "electrica"}
        quitar = [v for v in ELECTRICAS_OPCIONALES if v not in electricas] + \
                 [v for v in AMBIENTALES_FIJAS if v not in usadas_amb]
        con.executemany("DELETE FROM variables WHERE variable_id = ?", [(v,) for v in quitar])
        for v in ELECTRICAS_OPCIONALES:
            if v not in electricas:
                con.execute(f"ALTER TABLE mediciones_electricas DROP COLUMN {v}")
        for f in adic:
            vid = _txt(f["variable_id"])
            if vid in ELECTRICAS_OPCIONALES:     # códigos conocidos (voc_v, isc_a…): se usan los datos escritos
                if _txt(f["tipo"]) != "electrica":
                    raise sqlite3.IntegrityError(f"«{vid}» debe ser una variable eléctrica")
                con.execute("UPDATE variables SET nombre = ?, unidad = ?, agregacion = ? WHERE variable_id = ?",
                            [_txt(f["nombre"]), _txt(f.get("unidad")) or None, _txt(f.get("agregacion")) or "promedio", vid])
                continue
            con.execute("INSERT INTO variables (variable_id, nombre, unidad, tipo, agregacion) VALUES (?, ?, ?, ?, ?)",
                        [vid, _txt(f["nombre"]), _txt(f.get("unidad")) or None, _txt(f["tipo"]),
                         _txt(f.get("agregacion")) or "promedio"])
            if _txt(f["tipo"]) == "electrica":
                con.execute(f'ALTER TABLE mediciones_electricas ADD COLUMN "{vid}" REAL')
        for f in sen:
            sid = _txt(f["sensor_id"])
            con.execute("INSERT INTO sensores (sensor_id, variable_id, superficie_id, modulo_id, modelo) "
                        "VALUES (?, ?, ?, ?, ?)",
                        [sid, _txt(f["variable_id"]), _txt(f.get("superficie_id")) or None,
                         _txt(f.get("modulo_id")) or None, _txt(f.get("modelo")) or None])
            con.execute(f'ALTER TABLE mediciones_ambientales ADD COLUMN "{sid}" REAL')
        con.commit()
        con.execute("VACUUM")
    except sqlite3.Error as ex:
        con.close()
        destino.unlink(missing_ok=True)
        return [f"No se pudo crear la plantilla: {ex}"]
    con.close()
    return []


# --------------------------------------------------------------------------------------------
# Plantilla básica: solo columnas obligatorias (y las de sensores que definen irradiancia y
# temperatura de módulo). Las columnas opcionales del esquema completo se pueden agregar.
# --------------------------------------------------------------------------------------------
_FH = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]"
_F = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]"
ESQUEMA_BASICO = f"""
PRAGMA foreign_keys = ON;
CREATE TABLE instalacion (
    nombre  TEXT NOT NULL
);
CREATE TABLE tecnologias (
    tecnologia_id   TEXT PRIMARY KEY,
    nombre          TEXT NOT NULL,
    tipo            TEXT NOT NULL CHECK (tipo IN ({", ".join(repr(t) for t in TIPOS_TECNOLOGIA)})),
    potencia_stc_w  REAL NOT NULL CHECK (potencia_stc_w > 0),
    area_m2         REAL NOT NULL CHECK (area_m2 > 0)
);
CREATE TABLE superficies (
    superficie_id    TEXT PRIMARY KEY,
    nombre           TEXT NOT NULL,
    inclinacion_deg  REAL NOT NULL CHECK (inclinacion_deg BETWEEN 0 AND 90)
);
CREATE TABLE modulos (
    modulo_id      TEXT PRIMARY KEY,
    superficie_id  TEXT NOT NULL REFERENCES superficies (superficie_id),
    tecnologia_id  TEXT NOT NULL REFERENCES tecnologias (tecnologia_id)
);
CREATE TABLE variables (
    variable_id  TEXT PRIMARY KEY,
    nombre       TEXT NOT NULL,
    unidad       TEXT,
    tipo         TEXT NOT NULL CHECK (tipo IN ('electrica', 'ambiental')),
    agregacion   TEXT CHECK (agregacion IN ({", ".join(repr(a) for a in AGREGACIONES)}))
);
CREATE TABLE sensores (
    sensor_id      TEXT PRIMARY KEY,
    variable_id    TEXT NOT NULL REFERENCES variables (variable_id),
    superficie_id  TEXT REFERENCES superficies (superficie_id),
    modulo_id      TEXT REFERENCES modulos (modulo_id)
);
CREATE TABLE mediciones_electricas (
    fecha_hora      TEXT NOT NULL CHECK (fecha_hora GLOB '{_FH}'),
    modulo_id       TEXT NOT NULL REFERENCES modulos (modulo_id),
    potencia_max_w  REAL,
    PRIMARY KEY (modulo_id, fecha_hora)
) WITHOUT ROWID;
CREATE TABLE energia_diaria (
    fecha       TEXT NOT NULL CHECK (fecha GLOB '{_F}'),
    modulo_id   TEXT NOT NULL REFERENCES modulos (modulo_id),
    energia_wh  REAL CHECK (energia_wh >= 0),
    PRIMARY KEY (modulo_id, fecha)
) WITHOUT ROWID;
CREATE TABLE mediciones_ambientales (
    fecha_hora  TEXT PRIMARY KEY CHECK (fecha_hora GLOB '{_FH}')
) WITHOUT ROWID;
INSERT INTO variables (variable_id, nombre, unidad, tipo, agregacion) VALUES
    ('potencia_max_w',       'Potencia máxima',        'W',    'electrica', 'promedio'),
    ('irradiancia',          'Irradiancia',            'W/m²', 'ambiental', 'promedio'),
    ('temperatura_ambiente', 'Temperatura ambiente',   '°C',   'ambiental', 'promedio'),
    ('temperatura_modulo',   'Temperatura del módulo', '°C',   'ambiental', 'promedio'),
    ('humedad_relativa',     'Humedad relativa',       '%',    'ambiental', 'promedio'),
    ('velocidad_viento',     'Velocidad del viento',   'm/s',  'ambiental', 'promedio');
"""


def basica(destino):
    """Crea la plantilla básica en `destino`."""
    destino = Path(destino)
    destino.unlink(missing_ok=True)
    con = sqlite3.connect(destino)
    con.executescript(ESQUEMA_BASICO)
    con.commit()
    con.execute("VACUUM")
    con.close()


if __name__ == "__main__":
    import sys
    basica(sys.argv[1] if len(sys.argv) > 1 else AQUI.parent / "formato" / "plantilla.db")
    print("Listo")
