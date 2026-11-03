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

## Metodología

Los parámetros están en `procesamiento/metodologia.py` y son los mismos para cualquier instalación;
lo propio de cada una (potencia STC, área, sensores, límites de cada variable) viene de su base.

| Paso | Detalle |
|---|---|
| Ventana horaria | Solo datos de 5:00 a 19:00. |
| Irradiancia de cada módulo | La del sensor de irradiancia de su superficie, en el mismo minuto. |
| Filtro de módulos | Etapa 1: límites frente a la potencia STC (potencia fantasma / módulo muerto). Etapa 2: tubo estadístico Q20–Q80 por bins de 10 W/m², suavizado y ampliado. En superficies sin sensor de irradiancia solo se aplican límites de potencia. |
| Días válidos (energía) | Un día de un módulo cuenta si tiene ≥ 470 mediciones limpias. |
| Energía | La de la tabla `energia_diaria` si la base la trae; si no, integrando la potencia. |
| Eficiencia | `P / (G × área)`, solo con G ≥ 100 W/m². |
| Horas de sol pico | Suma horaria de la irradiancia / 1000, por superficie; día válido con ≥ 80 % de los minutos habituales. |
| Temperaturas | Entre −5 y 90 °C y dentro de los límites de cada variable. |
| Viento | Se descartan lecturas ≤ 0 y las que superan el máximo de la variable. |

## Estructura

```
├── app.py                 # punto de entrada (Dash): navegación, filtros, selector de fechas
├── plataforma/            # el visor
│   ├── config.py          # rutas y opciones de la aplicación
│   ├── datos.py           # consultas a data/visor.db
│   ├── graficas.py        # gráficas Plotly con el estilo de la plataforma
│   ├── componentes.py     # encabezado, pie, filtros, tarjetas
│   ├── paginas.py         # Clima, Energía y Desempeño
│   └── resumen_sumicol.py # pestaña Resumen del prototipo Sumicol
├── procesamiento/         # de la base de carga a la base de la plataforma
│   ├── validar_bd.py
│   ├── procesar.py
│   └── metodologia.py
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
