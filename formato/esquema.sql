-- =====================================================================
--  Formato de carga · Plataforma de monitoreo fotovoltaico
--  Un archivo SQLite (.db) por instalación, con estas 10 tablas (todas las columnas).
--  La plantilla básica (plantilla.db) trae solo las columnas obligatorias.
--  Guía completa: formato/guia_formato.md
--
--  Crear una base vacía desde la terminal:
--      sqlite3 mi_instalacion.db < esquema.sql
--  (o partir de plantilla.db y agregar las columnas opcionales que se necesiten)
-- =====================================================================
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
--  INFORMACIÓN DE LA INSTALACIÓN
-- ---------------------------------------------------------------------

-- Una sola fila con los datos generales del proyecto.
CREATE TABLE instalacion (
    nombre           TEXT NOT NULL,
    descripcion      TEXT,
    responsable      TEXT,
    ciudad           TEXT,
    pais             TEXT
);

-- Un tipo de módulo por fila. potencia_stc_w y area_m2 se usan para la eficiencia y los filtros.
CREATE TABLE tecnologias (
    tecnologia_id      TEXT PRIMARY KEY,
    nombre             TEXT NOT NULL,
    tipo               TEXT NOT NULL CHECK (tipo IN ('c-Si mono', 'c-Si poli', 'CdTe', 'CIGS', 'a-Si',
                                                     'perovskita', 'vidrio semitransparente', 'otro')),
    potencia_stc_w     REAL NOT NULL CHECK (potencia_stc_w > 0),
    area_m2            REAL NOT NULL CHECK (area_m2 > 0),
    transmitancia_pct  REAL CHECK (transmitancia_pct BETWEEN 0 AND 100),
    coef_temp_pmax     REAL,          -- %/°C
    fabricante         TEXT,
    modelo             TEXT
);

-- Caras, fachadas o cubiertas donde están los módulos.
-- orientacion vacía si es horizontal o si cambia en el tiempo (ver cronograma_orientaciones).
CREATE TABLE superficies (
    superficie_id    TEXT PRIMARY KEY,
    nombre           TEXT NOT NULL,
    inclinacion_deg  REAL NOT NULL CHECK (inclinacion_deg BETWEEN 0 AND 90),
    orientacion      TEXT CHECK (orientacion IN ('Norte', 'Noreste', 'Este', 'Sureste',
                                                 'Sur', 'Suroeste', 'Oeste', 'Noroeste')),
    descripcion      TEXT
);

-- Cada módulo con medición eléctrica. Su área es la de su tecnología.
CREATE TABLE modulos (
    modulo_id      TEXT PRIMARY KEY,
    superficie_id  TEXT NOT NULL REFERENCES superficies (superficie_id),
    tecnologia_id  TEXT NOT NULL REFERENCES tecnologias (tecnologia_id),
    nombre         TEXT
);

-- Todas las variables de la base: las fijas (ya escritas abajo) y las adicionales del usuario.
-- Para las eléctricas, variable_id es el nombre de la columna en mediciones_electricas.
CREATE TABLE variables (
    variable_id  TEXT PRIMARY KEY,
    nombre       TEXT NOT NULL,
    unidad       TEXT,
    tipo         TEXT NOT NULL CHECK (tipo IN ('electrica', 'ambiental')),
    agregacion   TEXT CHECK (agregacion IN ('promedio', 'suma', 'minimo', 'maximo'))   -- vacía = promedio
);

-- Una fila por cada columna de mediciones_ambientales: qué mide y dónde está conectado.
CREATE TABLE sensores (
    sensor_id      TEXT PRIMARY KEY,                       -- = nombre de la columna
    variable_id    TEXT NOT NULL REFERENCES variables (variable_id),
    superficie_id  TEXT REFERENCES superficies (superficie_id),
    modulo_id      TEXT REFERENCES modulos (modulo_id),
    modelo         TEXT,
    fabricante     TEXT,
    descripcion    TEXT,
    CHECK (variable_id <> 'irradiancia' OR superficie_id IS NOT NULL),       -- irradiancia: su superficie
    CHECK (variable_id <> 'temperatura_modulo' OR modulo_id IS NOT NULL),    -- temp. de módulo: su módulo
    CHECK (superficie_id IS NULL OR modulo_id IS NULL)                       -- nunca los dos
);

-- Opcional: periodos en que una superficie tuvo otra orientación (o inclinación).
CREATE TABLE cronograma_orientaciones (
    superficie_id    TEXT NOT NULL REFERENCES superficies (superficie_id),
    desde            TEXT NOT NULL CHECK (desde GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]'),
    hasta            TEXT CHECK (hasta GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]'),
    orientacion      TEXT NOT NULL CHECK (orientacion IN ('Norte', 'Noreste', 'Este', 'Sureste',
                                                          'Sur', 'Suroeste', 'Oeste', 'Noroeste')),
    inclinacion_deg  REAL CHECK (inclinacion_deg BETWEEN 0 AND 90),
    PRIMARY KEY (superficie_id, desde),
    CHECK (hasta IS NULL OR hasta > desde)
);

-- ---------------------------------------------------------------------
--  MEDICIONES
-- ---------------------------------------------------------------------

-- Una fila por módulo y lectura. potencia_max_w es obligatoria; las demás pueden quedar vacías.
-- Variables eléctricas adicionales: declararlas en `variables` y agregar la columna, p. ej.
--     ALTER TABLE mediciones_electricas ADD COLUMN ff REAL;
CREATE TABLE mediciones_electricas (
    fecha_hora      TEXT NOT NULL CHECK (fecha_hora GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]'),
    modulo_id       TEXT NOT NULL REFERENCES modulos (modulo_id),
    potencia_max_w  REAL,
    voc_v           REAL,
    isc_a           REAL,
    vmpp_v          REAL,
    impp_a          REAL,
    PRIMARY KEY (modulo_id, fecha_hora)
) WITHOUT ROWID;

-- Opcional: energía diaria calculada por el equipo. Si no está, la plataforma la calcula.
CREATE TABLE energia_diaria (
    fecha        TEXT NOT NULL CHECK (fecha GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    modulo_id    TEXT NOT NULL REFERENCES modulos (modulo_id),
    energia_wh   REAL CHECK (energia_wh >= 0),
    data_points  INTEGER CHECK (data_points >= 0),
    PRIMARY KEY (modulo_id, fecha)
) WITHOUT ROWID;

-- Una fila por lectura y una columna por sensor (cada una declarada en `sensores`):
--     ALTER TABLE mediciones_ambientales ADD COLUMN "IR1" REAL;
CREATE TABLE mediciones_ambientales (
    fecha_hora  TEXT PRIMARY KEY CHECK (fecha_hora GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]')
) WITHOUT ROWID;

-- ---------------------------------------------------------------------
--  VARIABLES FIJAS (borrar las filas de las que no se entreguen,
--  excepto potencia_max_w, que es obligatoria)
-- ---------------------------------------------------------------------
INSERT INTO variables (variable_id, nombre, unidad, tipo, agregacion) VALUES
    ('potencia_max_w',       'Potencia máxima',                     'W',    'electrica', 'promedio'),
    ('voc_v',                'Voltaje de circuito abierto',         'V',    'electrica', 'promedio'),
    ('isc_a',                'Corriente de cortocircuito',          'A',    'electrica', 'promedio'),
    ('vmpp_v',               'Voltaje en el punto de máxima potencia',   'V', 'electrica', 'promedio'),
    ('impp_a',               'Corriente en el punto de máxima potencia', 'A', 'electrica', 'promedio'),
    ('irradiancia',          'Irradiancia',                         'W/m²', 'ambiental', 'promedio'),
    ('temperatura_ambiente', 'Temperatura ambiente',                '°C',   'ambiental', 'promedio'),
    ('temperatura_modulo',   'Temperatura del módulo',              '°C',   'ambiental', 'promedio'),
    ('humedad_relativa',     'Humedad relativa',                    '%',    'ambiental', 'promedio'),
    ('velocidad_viento',     'Velocidad del viento',                'm/s',  'ambiental', 'promedio');
