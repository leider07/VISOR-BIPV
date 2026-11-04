"""
Validador del formato de carga de la plataforma de monitoreo fotovoltaico.

Revisa una base SQLite contra la guía (formato/guia_formato.md) y entrega:
  - ERRORES: impiden cargar la base (tablas o columnas obligatorias que faltan, códigos que no
    existen, fechas mal escritas, lecturas duplicadas, valores fuera de las listas…).
  - AVISOS: la base se puede cargar, pero algo se ignora o falta para alguna gráfica.
  - RESUMEN: qué contiene la base y qué páginas de la plataforma se podrán mostrar.

La base solo se lee; nunca se modifica.

Uso:
    python validar_bd.py mi_instalacion.db
Código de salida: 0 si no hay errores, 1 si hay errores.
"""
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

FECHA_HORA = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]"
FECHA = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]"

# tabla: (obligatoria, {columna: obligatoria})
TABLAS = {
    "instalacion": (True, {"nombre": True, "descripcion": False,
                           "responsable": False, "ciudad": False, "pais": False}),
    "tecnologias": (True, {"tecnologia_id": True, "nombre": True, "tipo": True, "potencia_stc_w": True,
                           "area_m2": True, "transmitancia_pct": False, "coef_temp_pmax": False,
                           "fabricante": False, "modelo": False}),
    "superficies": (True, {"superficie_id": True, "nombre": True, "inclinacion_deg": True,
                           "orientacion": False, "descripcion": False}),
    "modulos": (True, {"modulo_id": True, "superficie_id": True, "tecnologia_id": True, "nombre": False}),
    "variables": (True, {"variable_id": True, "nombre": True, "unidad": True, "tipo": True,
                         "agregacion": False}),
    "sensores": (True, {"sensor_id": True, "variable_id": True, "superficie_id": False,
                        "modulo_id": False, "modelo": False, "fabricante": False, "descripcion": False}),
    "cronograma_orientaciones": (False, {"superficie_id": True, "desde": True, "hasta": True,
                                         "orientacion": True, "inclinacion_deg": False}),
    "mediciones_electricas": (True, {"fecha_hora": True, "modulo_id": True, "potencia_max_w": True}),
    "energia_diaria": (False, {"fecha": True, "modulo_id": True, "energia_wh": True, "data_points": False}),
    "mediciones_ambientales": (True, {"fecha_hora": True}),
}
TIPOS_TECNOLOGIA = ["c-Si mono", "c-Si poli", "CdTe", "CIGS", "a-Si", "perovskita", "vidrio semitransparente", "otro"]
ORIENTACIONES = ["Norte", "Noreste", "Este", "Sureste", "Sur", "Suroeste", "Oeste", "Noroeste"]
AGREGACIONES = ["promedio", "suma", "minimo", "maximo"]
VARIABLES_FIJAS = {
    "potencia_max_w": "electrica", "voc_v": "electrica", "isc_a": "electrica", "vmpp_v": "electrica",
    "impp_a": "electrica", "irradiancia": "ambiental", "temperatura_ambiente": "ambiental",
    "temperatura_modulo": "ambiental", "humedad_relativa": "ambiental", "velocidad_viento": "ambiental",
}
NOMBRE_VALIDO = re.compile(r"^[A-Za-z0-9_]+$")
MAX_EJEMPLOS = 5


@dataclass
class Informe:
    errores: list = field(default_factory=list)
    avisos: list = field(default_factory=list)
    resumen: list = field(default_factory=list)

    def error(self, t): self.errores.append(t)
    def aviso(self, t): self.avisos.append(t)
    def info(self, t): self.resumen.append(t)


def q(nombre):
    return '"' + nombre.replace('"', '""') + '"'


def ejemplos(filas):
    vals = [", ".join(str(v) for v in f) if isinstance(f, (tuple, list)) else str(f) for f in filas[:MAX_EJEMPLOS]]
    return "; ".join(vals) + (" …" if len(filas) > MAX_EJEMPLOS else "")


class Validador:
    def __init__(self, ruta):
        self.ruta = Path(ruta)
        self.r = Informe()
        self.con = None
        self.cols = {}          # tabla -> [columnas]

    # --------------------------------------------------------------------------------------
    def uno(self, sql, *p):
        return self.con.execute(sql, p).fetchone()[0]

    def todos(self, sql, *p):
        return self.con.execute(sql, p).fetchall()

    def existe(self, tabla):
        return tabla in self.cols

    def col(self, tabla, col):
        """La columna entre comillas, o NULL si la tabla no la trae (columnas opcionales)."""
        return q(col) if col in self.cols.get(tabla, []) else "NULL"

    def ids(self, tabla, col):
        return {r[0] for r in self.todos(f"SELECT {q(col)} FROM {q(tabla)}")} if self.existe(tabla) else set()

    # --------------------------------------------------------------------------------------
    def ejecutar(self):
        if not self.ruta.is_file():
            self.r.error(f"No se encontró el archivo {self.ruta}")
            return self.r
        try:
            self.con = sqlite3.connect(f"{self.ruta.resolve().as_uri()}?mode=ro", uri=True)
            tablas = [r[0] for r in self.todos("SELECT name FROM sqlite_master WHERE type = 'table'")]
        except sqlite3.DatabaseError as e:
            self.r.error(f"El archivo no es una base SQLite válida ({e})")
            return self.r
        self.cols = {t: [c[1] for c in self.todos(f"PRAGMA table_info({q(t)})")] for t in tablas}

        if not self.estructura():
            return self.r          # sin las tablas obligatorias no tiene sentido seguir
        self.instalacion()
        self.tecnologias()
        self.superficies()
        self.modulos()
        self.variables()
        self.sensores()
        self.cronograma()
        self.mediciones_electricas()
        self.energia_diaria()
        self.mediciones_ambientales()
        self.paginas()
        self.con.close()
        return self.r

    # --------------------------------------------------------------------------------------
    def estructura(self):
        ok = True
        for t, (oblig, cols) in TABLAS.items():
            if not self.existe(t):
                if oblig:
                    self.r.error(f"Falta la tabla obligatoria `{t}`")
                    ok = False
                continue
            for c, c_oblig in cols.items():
                if c_oblig and c not in self.cols[t]:
                    self.r.error(f"Falta la columna obligatoria `{t}.{c}`")
                    ok = False
        otras = sorted(set(self.cols) - set(TABLAS) - {"sqlite_sequence", "sqlite_stat1"})
        if otras:
            self.r.aviso(f"Tablas que la plataforma no usa y se ignoran: {', '.join(otras)}")
        return ok

    def vacios(self, tabla, cols):
        for c in cols:
            if c in self.cols.get(tabla, []):
                n = self.uno(f"SELECT COUNT(*) FROM {q(tabla)} WHERE {q(c)} IS NULL OR TRIM({q(c)}) = ''")
                if n:
                    self.r.error(f"`{tabla}.{c}` está vacía en {n} fila(s) y es obligatoria")

    def duplicados(self, tabla, cols, que):
        lista = ", ".join(q(c) for c in cols)
        filas = self.todos(f"SELECT {lista}, COUNT(*) FROM {q(tabla)} GROUP BY {lista} HAVING COUNT(*) > 1 LIMIT 50")
        if filas:
            total = self.uno(f"SELECT COUNT(*) FROM (SELECT 1 FROM {q(tabla)} GROUP BY {lista} HAVING COUNT(*) > 1)")
            self.r.error(f"`{tabla}`: {total} {que} repetido(s) (ej.: {ejemplos([f[:-1] for f in filas])})")

    def en_lista(self, tabla, col, lista, permitir_vacio=True):
        if col not in self.cols.get(tabla, []):
            return
        marcas = ", ".join("?" * len(lista))
        cond = f"{q(col)} NOT IN ({marcas})" + (f" AND {q(col)} IS NOT NULL AND TRIM({q(col)}) <> ''" if permitir_vacio else "")
        malos = self.todos(f"SELECT DISTINCT {q(col)} FROM {q(tabla)} WHERE {cond}", *lista)
        if malos:
            self.r.error(f"`{tabla}.{col}` tiene valores no permitidos: {ejemplos([m[0] for m in malos])}. "
                         f"Permitidos: {', '.join(lista)}")

    def rango(self, tabla, col, mn=None, mx=None, que="valores"):
        if col not in self.cols.get(tabla, []):
            return
        cond = []
        if mn is not None: cond.append(f"{q(col)} < {mn}")
        if mx is not None: cond.append(f"{q(col)} > {mx}")
        n = self.uno(f"SELECT COUNT(*) FROM {q(tabla)} WHERE {q(col)} IS NOT NULL AND ({' OR '.join(cond)})")
        if n:
            if mx is None:
                limite = "mayor que 0" if mn and mn < 0.001 else f"mayor o igual a {mn}"
            elif mn is None:
                limite = f"menor o igual a {mx}"
            else:
                limite = f"entre {mn} y {mx}"
            self.r.error(f"`{tabla}.{col}`: {n} {que} no válido(s); debe ser {limite}")

    def referencia(self, tabla, col, destino, col_destino, opcional=False):
        if col not in self.cols.get(tabla, []) or not self.existe(destino):
            return
        filas = self.todos(f"SELECT DISTINCT t.{q(col)} FROM {q(tabla)} t LEFT JOIN {q(destino)} d "
                           f"ON t.{q(col)} = d.{q(col_destino)} WHERE d.{q(col_destino)} IS NULL "
                           f"AND t.{q(col)} IS NOT NULL")
        if filas:
            self.r.error(f"`{tabla}.{col}` usa códigos que no existen en `{destino}`: {ejemplos([f[0] for f in filas])}")

    def formato_fecha(self, tabla, col, patron, ejemplo, permitir_vacio=False):
        if col not in self.cols.get(tabla, []):
            return
        cond = f"NOT ({q(col)} GLOB '{patron}')" + (f" AND {q(col)} IS NOT NULL" if permitir_vacio else f" OR {q(col)} IS NULL")
        n = self.uno(f"SELECT COUNT(*) FROM {q(tabla)} WHERE {cond}")
        if n:
            ej = [r[0] for r in self.todos(f"SELECT {q(col)} FROM {q(tabla)} WHERE {cond} LIMIT {MAX_EJEMPLOS}")]
            self.r.error(f"`{tabla}.{col}`: {n} fecha(s) mal escrita(s) (ej.: {ejemplos(ej)}). Formato: {ejemplo}")

    def codigos(self, tabla, col):
        malos = [i for i in self.ids(tabla, col) if i is not None and not NOMBRE_VALIDO.match(str(i))]
        if malos:
            self.r.error(f"`{tabla}.{col}`: los códigos solo pueden tener letras sin tilde, números y _ "
                         f"(revisar: {ejemplos(sorted(map(str, malos)))})")

    # --------------------------------------------------------------------------------------
    def instalacion(self):
        n = self.uno("SELECT COUNT(*) FROM instalacion")
        if n != 1:
            self.r.error(f"`instalacion` debe tener exactamente 1 fila (tiene {n})")
        if n:
            nombre = self.uno("SELECT nombre FROM instalacion")
            if not nombre or not str(nombre).strip():
                self.r.error("`instalacion.nombre` está vacío")
            self.info(f"Instalación: {nombre}")

    def info(self, t):
        self.r.info(t)

    def tecnologias(self):
        n = self.uno("SELECT COUNT(*) FROM tecnologias")
        if not n:
            self.r.error("`tecnologias` está vacía")
        self.vacios("tecnologias", ["tecnologia_id", "nombre", "tipo", "potencia_stc_w", "area_m2"])
        self.duplicados("tecnologias", ["tecnologia_id"], "código(s)")
        self.codigos("tecnologias", "tecnologia_id")
        self.en_lista("tecnologias", "tipo", TIPOS_TECNOLOGIA, permitir_vacio=False)
        self.rango("tecnologias", "potencia_stc_w", 0.000001, None, "potencia(s)")
        self.rango("tecnologias", "area_m2", 0.000001, None, "área(s)")
        self.rango("tecnologias", "transmitancia_pct", 0, 100)
        self.info(f"Tecnologías: {n}")

    def superficies(self):
        n = self.uno("SELECT COUNT(*) FROM superficies")
        if not n:
            self.r.error("`superficies` está vacía")
        self.vacios("superficies", ["superficie_id", "nombre", "inclinacion_deg"])
        self.duplicados("superficies", ["superficie_id"], "código(s)")
        self.codigos("superficies", "superficie_id")
        self.rango("superficies", "inclinacion_deg", 0, 90, "inclinación(es)")
        self.en_lista("superficies", "orientacion", ORIENTACIONES)
        self.info(f"Superficies: {n}")

    def modulos(self):
        n = self.uno("SELECT COUNT(*) FROM modulos")
        if not n:
            self.r.error("`modulos` está vacío")
        self.vacios("modulos", ["modulo_id", "superficie_id", "tecnologia_id"])
        self.duplicados("modulos", ["modulo_id"], "código(s)")
        self.codigos("modulos", "modulo_id")
        self.referencia("modulos", "superficie_id", "superficies", "superficie_id")
        self.referencia("modulos", "tecnologia_id", "tecnologias", "tecnologia_id")
        self.info(f"Módulos: {n}")

    def variables(self):
        self.vacios("variables", ["variable_id", "nombre", "tipo"])
        self.duplicados("variables", ["variable_id"], "código(s)")
        self.codigos("variables", "variable_id")
        self.en_lista("variables", "tipo", ["electrica", "ambiental"], permitir_vacio=False)
        self.en_lista("variables", "agregacion", AGREGACIONES)     # vacía = promedio
        filas = self.todos("SELECT variable_id, tipo FROM variables")
        self.vars = dict(filas)
        if "potencia_max_w" not in self.vars:
            self.r.error("Falta la variable obligatoria `potencia_max_w` en `variables`")
        for v, t in self.vars.items():
            if v in VARIABLES_FIJAS and t != VARIABLES_FIJAS[v]:
                self.r.error(f"La variable fija `{v}` debe ser de tipo `{VARIABLES_FIJAS[v]}` (dice `{t}`)")
        fijas = [v for v in self.vars if v in VARIABLES_FIJAS]
        adic = [v for v in self.vars if v not in VARIABLES_FIJAS]
        self.info(f"Variables fijas: {', '.join(fijas) or 'ninguna'}")
        if adic:
            self.info(f"Variables adicionales (pestaña Explorar): {', '.join(adic)}")

    def sensores(self):
        self.vacios("sensores", ["sensor_id", "variable_id"])
        self.duplicados("sensores", ["sensor_id"], "código(s)")
        self.codigos("sensores", "sensor_id")
        self.referencia("sensores", "variable_id", "variables", "variable_id")
        self.referencia("sensores", "superficie_id", "superficies", "superficie_id")
        self.referencia("sensores", "modulo_id", "modulos", "modulo_id")
        filas = self.todos(f"SELECT sensor_id, variable_id, {self.col('sensores', 'superficie_id')}, "
                           f"{self.col('sensores', 'modulo_id')} FROM sensores")
        self.sens = {s: (v, sup, m) for s, v, sup, m in filas}
        for s, (v, sup, m) in self.sens.items():
            if v in self.vars and self.vars[v] != "ambiental":
                self.r.error(f"El sensor `{s}` mide `{v}`, que es una variable eléctrica: los sensores son solo para variables ambientales")
            if v == "irradiancia" and not sup:
                self.r.error(f"El sensor de irradiancia `{s}` necesita `superficie_id`")
            if v == "temperatura_modulo" and not m:
                self.r.error(f"El sensor de temperatura de módulo `{s}` necesita `modulo_id`")
            if sup and m:
                self.r.error(f"El sensor `{s}` tiene superficie y módulo a la vez: debe tener solo uno")
        por_sup = {}
        for s, (v, sup, _) in self.sens.items():
            if v == "irradiancia" and sup:
                por_sup.setdefault(sup, []).append(s)
        for sup, lista in por_sup.items():
            if len(lista) > 1:
                self.r.error(f"La superficie `{sup}` tiene {len(lista)} sensores de irradiancia ({', '.join(lista)}): "
                             "debe tener uno solo (une las columnas antes de cargar)")
        for sup in self.ids("superficies", "superficie_id") - set(por_sup):
            self.r.aviso(f"La superficie `{sup}` no tiene sensor de irradiancia: sin horas de sol pico ni eficiencia para sus módulos")
        self.info(f"Sensores: {len(self.sens)}")

    def cronograma(self):
        if not self.existe("cronograma_orientaciones"):
            return
        t = "cronograma_orientaciones"
        self.vacios(t, ["superficie_id", "desde", "orientacion"])
        self.referencia(t, "superficie_id", "superficies", "superficie_id")
        self.formato_fecha(t, "desde", FECHA_HORA, "AAAA-MM-DD HH:MM:SS")
        self.formato_fecha(t, "hasta", FECHA_HORA, "AAAA-MM-DD HH:MM:SS", permitir_vacio=True)
        self.en_lista(t, "orientacion", ORIENTACIONES, permitir_vacio=False)
        self.rango(t, "inclinacion_deg", 0, 90, "inclinación(es)")
        self.duplicados(t, ["superficie_id", "desde"], "periodo(s)")
        alreves = self.todos(f"SELECT superficie_id, desde FROM {t} WHERE hasta IS NOT NULL AND hasta <= desde")
        if alreves:
            self.r.error(f"`{t}`: periodos con `hasta` anterior o igual a `desde`: {ejemplos(alreves)}")
        cruces = []
        filas = self.todos(f"SELECT superficie_id, desde, hasta FROM {t} ORDER BY superficie_id, desde")
        for (s1, d1, h1), (s2, d2, h2) in zip(filas, filas[1:]):
            if s1 == s2 and (h1 is None or d2 < h1):
                cruces.append((s1, d1, d2))
        if cruces:
            self.r.error(f"`{t}`: periodos que se cruzan (superficie, inicio, inicio del siguiente): {ejemplos(cruces)}")
        sin = self.todos(f"SELECT superficie_id FROM superficies WHERE {self.col('superficies', 'orientacion')} IS NULL "
                         "AND inclinacion_deg > 0 "
                         f"AND superficie_id NOT IN (SELECT superficie_id FROM {t})")
        for (s,) in sin:
            self.r.aviso(f"La superficie `{s}` no tiene orientación fija ni periodos en el cronograma")
        self.info(f"Cronograma: {len(filas)} periodo(s)")

    def mediciones_electricas(self):
        t = "mediciones_electricas"
        cols = self.cols[t]
        self.formato_fecha(t, "fecha_hora", FECHA_HORA, "AAAA-MM-DD HH:MM:SS")
        self.vacios(t, ["modulo_id"])
        self.referencia(t, "modulo_id", "modulos", "modulo_id")
        self.duplicados(t, ["modulo_id", "fecha_hora"], "lectura(s) (módulo + fecha_hora)")
        electricas = {v for v, tipo in self.vars.items() if tipo == "electrica"}
        sobran = [c for c in cols if c not in ("fecha_hora", "modulo_id") and c not in electricas]
        if sobran:
            self.r.aviso(f"Columnas de `{t}` que no están en `variables` y se ignoran: {', '.join(sobran)}")
        faltan = sorted(electricas - set(cols))
        if faltan:
            self.r.error(f"Variables eléctricas declaradas en `variables` sin columna en `{t}`: {', '.join(faltan)}")
        self.solo_numeros(t, [c for c in cols if c in electricas])
        n, ini, fin = self.con.execute(f"SELECT COUNT(*), MIN(fecha_hora), MAX(fecha_hora) FROM {t}").fetchone()
        if not n:
            self.r.error(f"`{t}` está vacía")
        else:
            self.info(f"Mediciones eléctricas: {n:,} lecturas, del {ini} al {fin}")
            sin = self.todos(f"SELECT modulo_id FROM modulos WHERE modulo_id NOT IN (SELECT DISTINCT modulo_id FROM {t})")
            if sin:
                self.r.aviso(f"Módulos sin mediciones eléctricas: {ejemplos([s[0] for s in sin])}")
            if "potencia_max_w" in cols:
                vacias = self.uno(f"SELECT COUNT(*) FROM {t} WHERE potencia_max_w IS NULL")
                if vacias == n:
                    self.r.error("`potencia_max_w` está vacía en todas las lecturas")

    def energia_diaria(self):
        if not self.existe("energia_diaria"):
            self.info("Energía diaria: la calculará la plataforma a partir de la potencia")
            return
        t = "energia_diaria"
        self.formato_fecha(t, "fecha", FECHA, "AAAA-MM-DD")
        self.vacios(t, ["modulo_id"])
        self.referencia(t, "modulo_id", "modulos", "modulo_id")
        self.duplicados(t, ["modulo_id", "fecha"], "día(s) (módulo + fecha)")
        self.rango(t, "energia_wh", 0, None, "energía(s)")
        self.rango(t, "data_points", 0, None, "conteo(s)")
        n = self.uno(f"SELECT COUNT(*) FROM {t}")
        self.info(f"Energía diaria: {n:,} días-módulo" if n else "Energía diaria: tabla vacía, la calculará la plataforma")

    def mediciones_ambientales(self):
        t = "mediciones_ambientales"
        cols = [c for c in self.cols[t] if c != "fecha_hora"]
        self.formato_fecha(t, "fecha_hora", FECHA_HORA, "AAAA-MM-DD HH:MM:SS")
        self.duplicados(t, ["fecha_hora"], "fecha(s)")
        sobran = [c for c in cols if c not in self.sens]
        if sobran:
            self.r.aviso(f"Columnas de `{t}` que no están en `sensores` y se ignoran: {', '.join(sobran)}")
        faltan = [s for s in self.sens if s not in cols]
        if faltan:
            self.r.error(f"Sensores declarados en `sensores` sin columna en `{t}`: {', '.join(faltan)}")
        self.solo_numeros(t, [c for c in cols if c in self.sens])
        n, ini, fin = self.con.execute(f"SELECT COUNT(*), MIN(fecha_hora), MAX(fecha_hora) FROM {t}").fetchone()
        if not n:
            self.r.aviso(f"`{t}` está vacía: sin páginas de clima ni eficiencia")
        else:
            self.info(f"Mediciones ambientales: {n:,} lecturas, del {ini} al {fin}")

    def solo_numeros(self, tabla, columnas):
        for c in columnas:
            texto = self.uno(f"SELECT COUNT(*) FROM {q(tabla)} WHERE typeof({q(c)}) = 'text' AND TRIM({q(c)}) <> ''")
            if texto:
                self.r.error(f"`{tabla}.{c}`: {texto:,} valor(es) con texto en lugar de número")

    def paginas(self):
        hay = set(self.vars)
        amb = {v for v, _, _ in self.sens.values()}
        lineas = [
            ("Clima · irradiancia y horas de sol pico", "irradiancia" in amb),
            ("Clima · temperaturas", bool({"temperatura_ambiente", "temperatura_modulo"} & amb)),
            ("Clima · humedad", "humedad_relativa" in amb),
            ("Clima · viento", "velocidad_viento" in amb),
            ("Energía", "potencia_max_w" in hay),
            ("Desempeño · potencia vs irradiancia y eficiencia", "potencia_max_w" in hay and "irradiancia" in amb),
        ]
        self.info("Páginas: " + " · ".join(f"{'✓' if ok else '✗'} {p}" for p, ok in lineas))


def imprimir(r, ruta):
    print(f"\nValidación de {ruta}\n")
    if r.errores:
        print(f"ERRORES ({len(r.errores)}) — hay que corregirlos antes de cargar la base:")
        for e in r.errores:
            print(f"  ✗ {e}")
        print()
    if r.avisos:
        print(f"AVISOS ({len(r.avisos)}):")
        for a in r.avisos:
            print(f"  ! {a}")
        print()
    if r.resumen:
        print("RESUMEN:")
        for i in r.resumen:
            print(f"  · {i}")
        print()
    print("Resultado:", "LISTA PARA CARGAR" if not r.errores else f"NO SE PUEDE CARGAR ({len(r.errores)} error(es))")


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    r = Validador(sys.argv[1]).ejecutar()
    imprimir(r, sys.argv[1])
    sys.exit(1 if r.errores else 0)


if __name__ == "__main__":
    main()
