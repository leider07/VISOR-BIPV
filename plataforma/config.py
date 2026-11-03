"""
Configuración de la plataforma (visor).

Todo lo propio de cada instalación (superficies, módulos, sensores, nombres) viene de la base
data/visor.db, que genera procesamiento/procesar.py a partir de una base en formato de carga 1.1.
Aquí solo quedan rutas y opciones de la aplicación.
"""
import tempfile
from pathlib import Path

from procesamiento import parametros as M

RAIZ = Path(__file__).resolve().parent.parent          # carpeta del repositorio
DB_VISOR = RAIZ / "data" / "visor.db"

# Muestreo de la dispersión potencia vs irradiancia (el mismo del procesamiento)
DISPERSION_MINUTOS = M.DISPERSION_MINUTOS

# Instalación que tiene la pestaña Resumen propia (textos y fotos fijos, plataforma/resumen_sumicol.py).
# Para cualquier otra instalación la plataforma abre directo en las gráficas.
INSTALACION_CON_RESUMEN = "Prototipo BIPV Sumicol"

# Bases que cargan los visitantes en «Tus datos»: carpeta temporal, se borran a las 24 h
# (en el hosting gratuito además se pierden al reiniciar el servidor)
CARPETA_CARGAS = Path(tempfile.gettempdir()) / "visor_cargas"
HORAS_CONSERVAR_CARGAS = 24
# Tamaño máximo de archivo que se acepta (MB)
MAX_MB_BASE_CARGA = 20       # base en formato de carga 1.1: se procesa en el servidor
MAX_MB_BASE_PROCESADA = 40   # base ya procesada en el computador con procesar.py
