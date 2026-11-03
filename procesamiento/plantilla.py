"""
Genera una plantilla de carga (formato 1.1) a partir de la descripción de una instalación.

La usa el formulario de la pestaña «Tus datos»: con lo que se llena allí se crea un .db con las
tablas de información ya escritas y las tablas de mediciones vacías, con exactamente las columnas
declaradas (una por variable eléctrica y una por sensor).
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

    mod = _filas(d.get("modulos"))
    ids_mod = codigos("Módulos", mod, "modulo_id", "un módulo")
    for i, f in enumerate(mod, 1):
        if _txt(f.get("superficie_id")) not in ids_sup:
            e.append(f"Módulos, fila {i}: elige una superficie de la tabla Superficies.")
        if _txt(f.get("tecnologia_id")) not in ids_tec:
            e.append(f"Módulos, fila {i}: elige una tecnología de la tabla Tecnologías.")

    adic = _filas(d.get("adicionales"))
    reservados = set(ELECTRICAS_OPCIONALES + AMBIENTALES_FIJAS + ["potencia_max_w", "fecha_hora", "modulo_id"])
    ids_adic = set()
    for i, f in enumerate(adic, 1):
        c = _txt(f.get("variable_id"))
        if not c or not CODIGO.match(c):
            e.append(f"Variables adicionales, fila {i}: el código solo puede tener letras sin tilde, números y _.")
        elif c in reservados or c in ids_adic:
            e.append(f"Variables adicionales, fila {i}: el código «{c}» ya existe.")
        ids_adic.add(c)
        if not _txt(f.get("nombre")):
            e.append(f"Variables adicionales, fila {i}: falta el nombre.")
        if _txt(f.get("tipo")) not in ("electrica", "ambiental"):
            e.append(f"Variables adicionales, fila {i}: elige si es eléctrica o ambiental.")
        if _txt(f.get("agregacion")) not in AGREGACIONES:
            e.append(f"Variables adicionales, fila {i}: elige cómo se resume (promedio, suma, mínimo o máximo).")
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
        con.execute("INSERT INTO instalacion (nombre, version_formato, descripcion, responsable, ciudad, pais) "
                    "VALUES (?, '1.1', ?, ?, ?, ?)",
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
        for f in _filas(d.get("modulos")):
            con.execute("INSERT INTO modulos VALUES (?, ?, ?, ?)",
                        [_txt(f["modulo_id"]), _txt(f["superficie_id"]), _txt(f["tecnologia_id"]),
                         _txt(f.get("nombre")) or None])

        # Variables: se dejan solo las que se van a entregar
        sen = _filas(d.get("sensores"))
        usadas_amb = {_txt(f["variable_id"]) for f in sen}
        electricas = set(d.get("electricas") or [])
        quitar = [v for v in ELECTRICAS_OPCIONALES if v not in electricas] + \
                 [v for v in AMBIENTALES_FIJAS if v not in usadas_amb]
        con.executemany("DELETE FROM variables WHERE variable_id = ?", [(v,) for v in quitar])
        for v in ELECTRICAS_OPCIONALES:
            if v not in electricas:
                con.execute(f"ALTER TABLE mediciones_electricas DROP COLUMN {v}")
        for f in _filas(d.get("adicionales")):
            vid = _txt(f["variable_id"])
            con.execute("INSERT INTO variables (variable_id, nombre, unidad, tipo, agregacion) VALUES (?, ?, ?, ?, ?)",
                        [vid, _txt(f["nombre"]), _txt(f.get("unidad")) or None, _txt(f["tipo"]), _txt(f["agregacion"])])
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
