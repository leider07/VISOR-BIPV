"""
Genera formato/guia_formato.pdf a partir de formato/guia/guia.html y de la
captura del diagrama (diagrama.png, tomada en DBeaver con una base creada desde esquema.sql).

Herramienta para quien mantiene la plataforma (no la usa la app). Necesita Playwright con Chromium:
    pip install playwright && playwright install chromium
    python formato/guia/generar_pdf.py            # PDF
    python formato/guia/generar_pdf.py --png      # además, una imagen por página para revisar
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

AQUI = Path(__file__).resolve().parent

DESTINO = AQUI.parent / "guia_formato.pdf"
html = (AQUI / "guia.html").read_text(encoding="utf-8")
tmp = AQUI / "_guia_armada.html"
tmp.write_text(html, encoding="utf-8")
try:
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page()
        pag.goto(tmp.as_uri())
        pag.wait_for_timeout(500)          # fuentes
        pag.pdf(path=str(DESTINO), format="Letter", print_background=True, prefer_css_page_size=True)
        if "--png" in sys.argv:
            pag.set_viewport_size({"width": 816, "height": 1056})
            n = pag.evaluate("document.querySelectorAll('.pagina').length")
            for i in range(n):
                pag.locator(".pagina").nth(i).screenshot(path=str(AQUI / f"_pagina_{i + 1}.png"))
        nav.close()
finally:
    tmp.unlink(missing_ok=True)
print(f"Listo: {DESTINO}")
