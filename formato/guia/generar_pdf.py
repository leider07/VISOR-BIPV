"""
Genera formato/guia_formato.pdf a partir de formato/guia/guia.html.

Herramienta para quien mantiene la plataforma (no la usa la app). Necesita Playwright con Chromium:
    pip install playwright && playwright install chromium
    python formato/guia/generar_pdf.py
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

AQUI = Path(__file__).resolve().parent
ORIGEN = AQUI / "guia.html"
DESTINO = AQUI.parent / "guia_formato.pdf"

with sync_playwright() as p:
    nav = p.chromium.launch()
    pag = nav.new_page()
    pag.goto(ORIGEN.as_uri())
    pag.wait_for_timeout(500)          # fuentes
    pag.pdf(path=str(DESTINO), format="Letter", print_background=True, prefer_css_page_size=True)
    nav.close()
print(f"Listo: {DESTINO}")
