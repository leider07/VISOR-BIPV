"""
Genera assets/docs/manual_uso.pdf a partir de manual/manual.html y de las capturas de manual/img/.

Herramienta para quien mantiene la plataforma (no la usa la app). Necesita Playwright con Chromium:
    pip install playwright && playwright install chromium
    python manual/generar_pdf.py            # PDF
    python manual/generar_pdf.py --png      # además, una imagen por página para revisar
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

AQUI = Path(__file__).resolve().parent
DESTINO = AQUI.parent / "assets" / "docs" / "manual_uso.pdf"

DESTINO.parent.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    nav = p.chromium.launch()
    pag = nav.new_page()
    pag.goto((AQUI / "manual.html").as_uri())
    pag.wait_for_timeout(800)          # fuentes e imágenes
    pag.pdf(path=str(DESTINO), format="Letter", print_background=True, prefer_css_page_size=True)
    if "--png" in sys.argv:
        pag.set_viewport_size({"width": 816, "height": 1056})
        n = pag.evaluate("document.querySelectorAll('.pagina').length")
        for i in range(n):
            pag.locator(".pagina").nth(i).screenshot(path=str(AQUI / f"_pagina_{i + 1}.png"))
    nav.close()
print(f"Listo: {DESTINO}")
