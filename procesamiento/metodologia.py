"""
Parámetros de la metodología de procesamiento de la plataforma.

Son los mismos para cualquier instalación. Lo propio de cada instalación (potencia STC, área,
sensores, límites de cada variable) viene de su base en formato 1.1.
"""

# Ventana horaria analizada: desde HORA_INICIO:00 hasta antes de HORA_FIN:00
HORA_INICIO = 5
HORA_FIN = 19

# --- Filtro híbrido de mediciones eléctricas -------------------------------------------------
# Etapa 1: límites físicos frente a la potencia STC de la tecnología
IRR_MIN = 10            # W/m²
IRR_MAX = 1300          # W/m²
IRR_LOGICA = 100        # W/m², umbral para "potencia fantasma" / "módulo muerto"
MIN_P_PCT = 0.005       # fracción de la potencia STC por debajo de la cual se descarta
# Potencia fantasma: fracción de la STC que no se puede superar con G < IRR_LOGICA.
# En vidrios semitransparentes depende de la transmitancia (más transmitancia, más margen).
GHOST_PCT = 0.05
GHOST_PCT_POR_TRANSMITANCIA = {10: 0.04, 30: 0.05, 40: 0.05, 80: 0.06}
# Etapa 2: "tubo" estadístico sobre la densidad de potencia (W/m²)
TUBO_BIN = 10
TUBO_Q_BAJO, TUBO_Q_ALTO = 0.20, 0.80
TUBO_VENTANA = 15
TUBO_EXPANSION = 0.5
TUBO_MARGEN_MIN = 4.0

# Módulos en superficies SIN sensor de irradiancia: no se puede aplicar el filtro híbrido; solo se
# descartan potencias negativas o mayores que esta fracción de la potencia STC
P_MAX_SIN_IRR = 1.3

# Un día de un módulo es válido para energía con al menos este número de mediciones limpias
UMBRAL_REGISTROS_DIA = 470

# Eficiencia: solo minutos con irradiancia >= este valor
IRR_MIN_EFICIENCIA = 100

# Un día es válido para irradiancia / horas de sol pico con al menos esta fracción de los
# minutos que el equipo registra en un día normal
FRACCION_MIN_DIA_IRR = 0.80
MINUTOS_ESPERADOS_DIA = 720   # el equipo de Sumicol medía de 6:00 a 18:00

# Viento: se descartan lecturas <= 0 (calma o sin dato)
VIENTO_MIN_EXCLUSIVO = 0.0
# Temperaturas plausibles (°C), además de los límites de cada variable
TEMP_MIN, TEMP_MAX = -5.0, 90.0

# Muestreo para la gráfica de dispersión potencia vs irradiancia
DISPERSION_MINUTOS = 10
DISPERSION_G_MIN = 20
