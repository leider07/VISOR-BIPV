# Formato de carga · Plataforma de monitoreo fotovoltaico

La plataforma recibe **un archivo SQLite (`.db`) por instalación** con 10 tablas: 7 describen la
instalación y 3 guardan las mediciones. Sirve para cualquier tecnología fotovoltaica. Los datos se
suben **ya organizados, corregidos y depurados** como cada usuario considere conveniente
(calibraciones aplicadas, cambios de sensor resueltos, datos erróneos retirados): la plataforma es un
**visor** y muestra los datos tal como se cargan, sin filtrarlos.

Archivos de esta carpeta:

| Archivo | Para qué |
|---|---|
| `plantilla.db` | Plantilla básica: las tablas con solo sus columnas obligatorias y las variables fijas ya escritas (las columnas opcionales se agregan si se necesitan) |
| `esquema.sql` | Las 10 tablas con todas sus columnas, en SQL (`sqlite3 mi_instalacion.db < esquema.sql`) |
| `guia_formato.md` | Esta guía |

Los ejemplos corresponden al prototipo BIPV de Sumicol, el primer caso cargado.

## Las 10 tablas

| Tabla | | Contenido |
|---|---|---|
| `instalacion` | obligatoria | Una fila: nombre y descripción del proyecto |
| `tecnologias` | obligatoria | Cada tipo de módulo: potencia STC, área, transmitancia… |
| `superficies` | obligatoria | Caras, fachadas o cubiertas: inclinación y orientación |
| `modulos` | obligatoria | Cada módulo medido: superficie y tecnología |
| `variables` | obligatoria | Variables fijas y adicionales |
| `sensores` | obligatoria | Qué mide cada columna ambiental y dónde está conectado |
| `cronograma_orientaciones` | opcional | Periodos en que una superficie cambió de orientación |
| `mediciones_electricas` | obligatoria | Una fila por módulo y lectura; una columna por variable eléctrica |
| `energia_diaria` | opcional | Energía por día y módulo, si ya está calculada |
| `mediciones_ambientales` | obligatoria | Una fila por lectura; una columna por sensor |

```
tecnologias ──< modulos >── superficies ──< cronograma_orientaciones
                  │  │           │
                  │  └──< sensores (modulo_id si es temperatura de módulo)
                  │              │ (superficie_id si es irradiancia)
                  │      variables ──< sensores
                  │          │
                  ├──< mediciones_electricas   (columnas = variable_id eléctricas)
                  └──< energia_diaria
     sensores ──< mediciones_ambientales       (columnas = sensor_id)
```

## Reglas generales

- **Nombres exactos**: tablas y columnas como en esta guía (minúsculas, sin tildes ni espacios).
  Toda columna de medición que no esté en `variables` o en `sensores` se ignora con un aviso.
- **Fecha y hora**: texto `AAAA-MM-DD HH:MM:SS` en hora local; fechas solas `AAAA-MM-DD`.
  El rango del proyecto se calcula de los datos.
- **Intervalo**: recomendado 1 minuto, aceptado hasta 15. Las tablas se cruzan por minuto.
- **Datos faltantes**: celda vacía (NULL). Nunca 0, -999 o texto.
- **Datos depurados**: la plataforma no filtra. Lo que se cargue es lo que se ve: si hay lecturas
  erróneas, horas que no interesan o días incompletos, se retiran antes de cargar.
- **Códigos** (`_id`): texto corto y único que tú eliges; igual en todas las tablas.
- **Unidades**: las fijas usan W, V, A, Wh, W/m², °C, %, m/s. Las adicionales declaran la suya.
- **Inclinación**: 0° horizontal, 90° vertical. **Orientación**: Norte, Noreste, Este, Sureste,
  Sur, Suroeste, Oeste o Noroeste.

## Columnas

● obligatoria · ○ opcional

### `instalacion` (una sola fila)

| Columna | Tipo | | Descripción | Sumicol |
|---|---|---|---|---|
| `nombre` | texto | ● | Nombre para el público | Prototipo BIPV Sumicol |
| `descripcion` | texto | ○ | Texto corto | 12 vidrios FV semitransparentes en 3 caras |
| `responsable` | texto | ○ | Grupo o entidad | Proyecto Integra · UdeA |
| `ciudad`, `pais` | texto | ○ | Ubicación general | —, Colombia |

### `tecnologias`

| Columna | Tipo | | Descripción | Sumicol |
|---|---|---|---|---|
| `tecnologia_id` | texto | ● | Código único | LT10 |
| `nombre` | texto | ● | Nombre en gráficas y filtros | Vidrio 10 % |
| `tipo` | texto | ● | `c-Si mono`, `c-Si poli`, `CdTe`, `CIGS`, `a-Si`, `perovskita`, `vidrio semitransparente`, `otro` | vidrio semitransparente |
| `potencia_stc_w` | número | ● | Potencia nominal STC (W) | 90 |
| `area_m2` | número | ● | Área del módulo (m²) | 0.72 |
| `transmitancia_pct` | número | ○ | Transmitancia visible (%) | 10 |
| `coef_temp_pmax` | número | ○ | Coeficiente de temperatura de la potencia (%/°C) | — |
| `fabricante`, `modelo` | texto | ○ | Referencia comercial | — |

### `superficies`

| Columna | Tipo | | Descripción | Sumicol |
|---|---|---|---|---|
| `superficie_id` | texto | ● | Código único | inclinada |
| `nombre` | texto | ● | Nombre para el público | Cara inclinada |
| `inclinacion_deg` | número | ● | 0–90° | 60 |
| `orientacion` | texto | ○ | Fija; vacía si es horizontal o si cambia | (vacía, rota) |
| `descripcion` | texto | ○ | Texto corto | Se giró entre Norte, Sur, Este y Oeste |

### `modulos`

| Columna | Tipo | | Descripción | Sumicol |
|---|---|---|---|---|
| `modulo_id` | texto | ● | Código único | Eload3_P2 |
| `superficie_id` | texto | ● | Existe en `superficies` | superior |
| `tecnologia_id` | texto | ● | Existe en `tecnologias` | LT10 |
| `nombre` | texto | ○ | Si falta, se usa el de la tecnología | — |

### `variables`

| Columna | Tipo | | Descripción | Ejemplo |
|---|---|---|---|---|
| `variable_id` | texto | ● | Código; en las eléctricas, nombre de la columna en `mediciones_electricas` | ff |
| `nombre` | texto | ● | Nombre para gráficas | Fill factor |
| `unidad` | texto | ● | Unidad (vacía si no tiene) | — |
| `tipo` | texto | ● | `electrica` o `ambiental` | electrica |
| `agregacion` | texto | ○ | `promedio`, `suma`, `minimo` o `maximo` (resumen por hora); vacía = `promedio` | promedio |

Variables fijas (la plantilla básica trae la potencia y las ambientales; `voc_v`, `isc_a`, `vmpp_v` e `impp_a` se agregan si se miden):

| variable_id | Tipo | Unidad | | Dónde se usa |
|---|---|---|---|---|
| `potencia_max_w` | electrica | W | ● | Energía, Desempeño, eficiencia |
| `voc_v`, `isc_a`, `vmpp_v`, `impp_a` | electrica | V, A | ○ | Explorar |
| `irradiancia` | ambiental | W/m² | ○ | Clima, horas de sol pico, Desempeño |
| `temperatura_ambiente` | ambiental | °C | ○ | Clima |
| `temperatura_modulo` | ambiental | °C | ○ | Clima |
| `humedad_relativa` | ambiental | % | ○ | Clima |
| `velocidad_viento` | ambiental | m/s | ○ | Clima |

### `sensores`

| Columna | Tipo | | Descripción | Sumicol |
|---|---|---|---|---|
| `sensor_id` | texto | ● | Nombre de la columna en `mediciones_ambientales` | TS9 |
| `variable_id` | texto | ● | Existe en `variables` (tipo ambiental) | temperatura_modulo |
| `superficie_id` | texto | ○ | **Obligatoria si es irradiancia** | — |
| `modulo_id` | texto | ○ | **Obligatoria si es temperatura de módulo** | Eload3_P1 |
| `modelo`, `fabricante` | texto | ○ | Sección de equipos | NTC B3950 10K |
| `descripcion` | texto | ○ | Notas | — |

Temperatura ambiente, humedad y viento no llevan superficie ni módulo: son del sitio.

### `cronograma_orientaciones` (opcional)

| Columna | Tipo | | Descripción |
|---|---|---|---|
| `superficie_id` | texto | ● | Existe en `superficies` |
| `desde` | fecha y hora | ● | Inicio del periodo |
| `hasta` | fecha y hora | ○ | Fin; vacío = hasta el final |
| `orientacion` | texto | ● | Orientación en ese periodo |
| `inclinacion_deg` | número | ○ | Solo si también cambió |

Los periodos de una superficie no se cruzan. Sumicol: cada periodo `30E90W` son 2 filas
(inclinada · Este, vertical · Oeste).

### `mediciones_electricas`

| Columna | Tipo | | Descripción |
|---|---|---|---|
| `fecha_hora` | fecha y hora | ● | Momento de la lectura |
| `modulo_id` | texto | ● | Existe en `modulos` |
| `potencia_max_w` | número | ● | Potencia máxima (W) |
| `voc_v`, `isc_a`, `vmpp_v`, `impp_a` | número | ○ | Parámetros de la curva I-V |
| `<variable adicional>` | número | ○ | Una columna por variable eléctrica adicional |

Una fila por módulo y lectura; no se repite módulo + fecha_hora.

### `energia_diaria` (opcional)

| Columna | Tipo | | Descripción |
|---|---|---|---|
| `fecha` | fecha | ● | Día |
| `modulo_id` | texto | ● | Existe en `modulos` |
| `energia_wh` | número | ● | Energía del día (Wh) |
| `data_points` | entero | ○ | Número de lecturas usadas en el cálculo (informativo) |

Si no está, la plataforma calcula la energía a partir de `potencia_max_w`.

### `mediciones_ambientales`

| Columna | Tipo | | Descripción |
|---|---|---|---|
| `fecha_hora` | fecha y hora | ● | Momento de la lectura (única por fila) |
| `<sensor_id>` | número | ● | Una columna por sensor, en la unidad de su variable |

Ejemplo Sumicol: `fecha_hora, IR1, IR2, IR3, TA4, RH1, W_Sp23, TS8, TS9, TS10, TS11`.
Con `sensores` se sabe que `TS9` es la temperatura del módulo `Eload3_P1`, que según `modulos`
está en la cara superior y es el vidrio de 40 %.

## Cómo crear la base

1. Llena el formulario de la plataforma o copia `plantilla.db`.
2. Llena `instalacion`, `tecnologias`, `superficies`, `modulos` y `sensores`, y agrega a
   `variables` tus variables adicionales.
3. Agrega las columnas que faltan (el formulario ya las crea). Con la plantilla básica, también
   las columnas opcionales que quieras usar:
   ```sql
   ALTER TABLE mediciones_ambientales ADD COLUMN "IR1" REAL;   -- un sensor
   ALTER TABLE mediciones_electricas  ADD COLUMN ff REAL;      -- una variable adicional
   ALTER TABLE tecnologias ADD COLUMN transmitancia_pct REAL;  -- una columna opcional
   ```
4. Copia las mediciones con Python, DB Browser for SQLite u otra herramienta.
5. Sube el archivo: la plataforma lo revisa y lista los errores antes de aceptarlo.

La plantilla rechaza fechas mal escritas, lecturas duplicadas, valores fuera de las listas y
códigos que no existen (estos últimos solo con `PRAGMA foreign_keys = ON`, que DB Browser activa
por defecto; la plataforma los revisa igual al cargar).

## Qué muestra la plataforma según las variables

| Página · gráfica | Necesita |
|---|---|
| Clima · irradiancia por hora, horas de sol pico, matriz | `irradiancia` |
| Clima · temperaturas | `temperatura_ambiente` y/o `temperatura_modulo` |
| Clima · humedad | `humedad_relativa` |
| Clima · viento | `velocidad_viento` |
| Energía | `potencia_max_w` (o `energia_diaria`) |
| Desempeño · potencia por hora | `potencia_max_w` |
| Desempeño · potencia vs irradiancia, eficiencia | `potencia_max_w` + `irradiancia` de la superficie |
| Explorar | Cualquier variable, incluidas las adicionales |

VOC, ISC, VMPP, IMPP y las variables adicionales se ven en **Explorar** (variable, módulos o
sensores, eje horizontal: tiempo / hora del día / otra variable, y fechas).
