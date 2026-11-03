# Plataforma de monitoreo fotovoltaico · Proyecto Integra

Plataforma web (Dash + Plotly) para visualizar datos históricos de instalaciones fotovoltaicas:
clima y recurso solar, energía generada y desempeño (potencia y eficiencia) de cada módulo.

El primer caso es el **prototipo BIPV de Sumicol**: 12 vidrios fotovoltaicos semitransparentes
(10, 30, 40 y 80 % de transmitancia) en tres caras (0°, 60° y 90°).

## Cómo funciona

```
mi_instalacion.db  (formato de carga 1.1, ver formato/)
   │  python procesamiento/procesar.py mi_instalacion.db     ← valida, filtra y resume
   ▼
data/visor.db      (base liviana de la plataforma)
   │  python app.py
   ▼
http://127.0.0.1:8050
```

La plataforma se arma con lo que trae la base: superficies, módulos, tecnologías y variables.
Cada gráfica aparece solo si hay datos para ella (por ejemplo, sin sensor de viento no hay
gráficas de viento). La pestaña **Resumen** es propia de Sumicol; para otras instalaciones la
plataforma abre directamente en las gráficas.

La pestaña **Explorar** muestra cualquier variable de la base (también las adicionales que declare
cada instalación, como el fill factor) por módulo o por sensor: en el tiempo, a lo largo del día o
contra otra variable, y permite descargar los datos en CSV.

## Tus datos: cada visitante puede ver su propia instalación

La pestaña **Tus datos** tiene dos partes:

1. **Crea tu plantilla:** un formulario con tablas editables (instalación, tecnologías, superficies,
   módulos, variables y sensores). Genera un `.db` en formato 1.1 con las tablas de información ya
   llenas y las de mediciones vacías, con exactamente las columnas declaradas.
2. **Carga tu base:** se acepta
   - la base en formato de carga (hasta 20 MB): se valida y se procesa en el servidor;
   - o, si es más grande, la base ya procesada en el computador con `procesamiento/procesar.py`
     (hasta 40 MB).

La base cargada **solo la ve quien la subió**, en esa pestaña del navegador; se guarda en una carpeta
temporal del servidor y se borra a las 24 horas (en el plan gratuito de Render, también al
reiniciarse el servidor). Los límites están en `plataforma/config.py`.

## Usarla en el computador

Abre una terminal en esta carpeta y ejecuta:

```bash
pip install -r requirements.txt                          # 1. dependencias (la primera vez)
python procesamiento/validar_bd.py mi_instalacion.db     # 2. (opcional) revisar la base
python procesamiento/procesar.py mi_instalacion.db       # 3. generar data/visor.db
python app.py                                            # 4. abrir http://127.0.0.1:8050
```

`data/visor.db` ya viene generada con los datos de Sumicol, así que para verla basta con los
pasos 1 y 4.

## Preparar una base para cargar

En `formato/` está todo lo necesario:

| Archivo | Para qué |
|---|---|
| `guia_formato.md` | Guía del formato de carga 1.1: las 10 tablas, sus columnas y reglas |
| `plantilla_v1.1.db` | Base vacía con las tablas creadas y las variables fijas escritas |
| `esquema.sql` | Las mismas tablas en SQL |

`procesamiento/validar_bd.py` revisa una base y lista los errores en lenguaje claro antes de
procesarla.

## La plataforma es un visor

La plataforma **no filtra datos**: muestra lo que trae la base tal como se cargó. Cada instalación
depura sus datos antes de cargarlos (Sumicol, por ejemplo, aplica su propio filtro, ventana horaria
y días válidos en su script de preparación, fuera de este repositorio).

`procesamiento/procesar.py` solo resume los datos para que las páginas carguen rápido
(parámetros en `procesamiento/parametros.py`):

| Resumen | Detalle |
|---|---|
| Promedios por hora | Potencia, irradiancia, temperaturas, humedad, viento y todas las variables de Explorar. |
| Irradiancia de cada módulo | La del sensor de irradiancia de su superficie, en el mismo minuto. |
| Energía | La de la tabla `energia_diaria` si la base la trae; si no, integrando la potencia. |
| Eficiencia | `P / (G × área)`, solo con G ≥ 100 W/m² (con poca luz el cociente no tiene sentido). |
| Horas de sol pico | Suma de los promedios horarios de irradiancia / 1000, por día y superficie. |
| Dispersión potencia–irradiancia | Promedios de 10 minutos, desde 20 W/m². |

## Estructura

```
├── app.py                 # punto de entrada (Dash): navegación, filtros, selector de fechas
├── plataforma/            # el visor
│   ├── config.py          # rutas y opciones de la aplicación
│   ├── datos.py           # consultas a data/visor.db
│   ├── graficas.py        # gráficas Plotly con el estilo de la plataforma
│   ├── componentes.py     # encabezado, pie, filtros, tarjetas
│   ├── paginas.py         # Clima, Energía, Desempeño y Explorar
│   ├── resumen_sumicol.py # pestaña Resumen del prototipo Sumicol
│   └── tus_datos.py       # pestaña Tus datos: formulario de plantilla y carga de bases
├── procesamiento/         # de la base de carga a la base de la plataforma
│   ├── validar_bd.py
│   ├── procesar.py
│   ├── plantilla.py       # crea plantillas desde el formulario
│   └── parametros.py
├── formato/               # guía, esquema y plantilla del formato de carga
├── data/visor.db          # base de la plataforma (Sumicol)
└── assets/                # css/, fonts/ (con sus licencias OFL), img/ (logos, iconos, sumicol)
```

## Publicarla en internet (Render, plan gratuito)

1. **GitHub:** este repositorio (`visor-bipv-sumicol`).
2. **Render:** https://render.com con tu cuenta de GitHub → *New → Web Service* → elige el
   repositorio y configura:
   - Language: **Python 3**
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:server --workers 1 --threads 4 --timeout 120`
   - Instance Type: **Free**

   (También puedes usar *New → Blueprint*, que toma estos valores de `render.yaml`.)
3. Render entrega un enlace tipo `https://visor-bipv-sumicol.onrender.com`.

**Actualizar la plataforma:** genera `data/visor.db` con `procesar.py`, haz commit y push.
Render vuelve a publicar automáticamente.

**Límites del plan gratuito:** se "duerme" tras 15 minutos sin visitas (la siguiente visita tarda
cerca de un minuto), tiene poca CPU y un límite mensual de tráfico. La app usa unos 160 MB de los
512 MB de memoria disponibles.
