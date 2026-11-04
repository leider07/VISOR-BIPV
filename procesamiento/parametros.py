"""
Parámetros de cálculo y de visualización de la plataforma.

La plataforma es un visor: muestra los datos tal como se cargan y no los filtra. Cualquier limpieza
(ventanas horarias, filtros, días válidos) la hace cada instalación antes de armar su base.
"""

# Eficiencia: se calcula solo con irradiancia >= este valor (con poca luz el cociente P / (G·A) no tiene sentido)
IRR_MIN_EFICIENCIA = 100

# Gráfica de dispersión potencia vs irradiancia: promedios de N minutos, desde esta irradiancia
DISPERSION_MINUTOS = 10
DISPERSION_G_MIN = 20

# Energía integrada (si la base no trae energia_diaria): tiempo máximo entre lecturas que se integra (s)
DT_MAX_INTEGRACION = 900
