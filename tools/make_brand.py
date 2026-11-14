#!/usr/bin/env python3
"""Genera los íconos de la app, el favicon y la imagen para redes de Ciber Radar.

La marca es tipográfica, como la cabecera de un diario: el nombre en Archivo angosta, con las dos R
del medio espalda con espalda (la de CIBER, espejada). Los íconos llevan solo esas dos R.

Herramienta de desarrollo: usa Playwright con Chromium para pasar el HTML a PNG.
    PLAYWRIGHT_BROWSERS_PATH=… python tools/make_brand.py
"""
from __future__ import annotations

import asyncio
import base64
import struct
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
ICONS = SITE / "icons"
PAPER, INK, GREY, RED = "#ffffff", "#111111", "#333333", "#c8102e"


def fonts_css() -> str:
    fonts = (SITE / "fonts").resolve().as_uri()
    return (f'@font-face {{ font-family: "Archivo"; src: url("{fonts}/archivo-latin-wdth-normal.woff2"); font-weight: 100 900; font-stretch: 62% 125%; }}')


def icon_html(size: int, scale: float = 1.0) -> str:
    """El mismo dibujo que el logo del pie: las dos R entre una línea arriba y otra abajo (línea = .085em,
    mayúscula de .94em y .14em de aire alrededor). scale achica para la zona segura."""
    em = size * scale * .6 / 1.39  # el dibujo (1.39em de alto) ocupa el 60 % del alto del ícono
    line = max(2.0, em * .085)
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>{fonts_css()}
html, body {{ margin: 0; width: {size}px; height: {size}px; overflow: hidden; }}
body {{ display: grid; place-items: center; background: {PAPER}; }}
b {{ display: flex; align-items: center; box-sizing: border-box; height: {em * 1.22 + 2 * line:.2f}px; padding: 0 {em * .14:.2f}px; border-block: {line:.2f}px solid {INK};
     font: 800 {em:.2f}px/1 "Archivo"; font-stretch: 62%; }}
i, u {{ display: block; font-style: normal; text-decoration: none; font-size: 1.3663em; line-height: .688; translate: 0 .01em; color: {RED}; }}
i {{ transform: scaleX(-1); margin-right: -.015em; }}
</style></head><body><b><i>R</i><u>R</u></b></body></html>'''


def og_html() -> str:
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>{fonts_css()}
html, body {{ margin: 0; width: 1200px; height: 630px; overflow: hidden; }}
body {{ display: grid; place-items: center; background: {PAPER}; color: {INK}; }}
.plate {{ display: flex; flex-direction: column; align-items: center; }}
h1 {{ display: flex; align-items: center; gap: .03em; margin: 0; font: 800 170px/.92 "Archivo"; font-stretch: 62%; white-space: nowrap; }}
h1 .side {{ display: block; padding: .07em .04em .01em; border-block: .085em solid {INK}; line-height: .86; }}
h1 .rr {{ display: flex; height: .688em; font-size: 1.3663em; line-height: .688; color: {RED}; }}
h1 .rr i, h1 .rr u {{ font-style: normal; text-decoration: none; display: block; translate: 0 .01em; }}
h1 .rr i {{ transform: scaleX(-1); margin-right: -.015em; }}
p {{ margin: 34px 0 0; font: 700 27px/1.2 "Archivo"; font-stretch: 80%; letter-spacing: .03em; color: {INK}; white-space: nowrap; }}
</style></head><body><div class="plate"><h1><span class="side">CIBE</span><span class="rr"><i>R</i><u>R</u></span><span class="side">ADAR</span></h1>
<p>NOTICIAS DE CIBERSEGURIDAD · ARGENTINA, LATINOAMÉRICA Y EL MUNDO</p></div></body></html>'''


def ico(png: bytes, size: int) -> bytes:
    """Un .ico con un PNG adentro, formato que leen todos los navegadores actuales."""
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(png), 6 + 16)
    return header + entry + png


async def render() -> None:
    # Los nombres llevan "rr-": al cambiar el dibujo hay que cambiar el nombre, porque navegadores, el service
    # worker y los sistemas que instalan la app guardan el ícono por su URL y no lo vuelven a pedir.
    from playwright.async_api import async_playwright

    ICONS.mkdir(parents=True, exist_ok=True)
    jobs = [
        ("rr-192.png", icon_html(192), 192),
        ("rr-512.png", icon_html(512), 512),
        ("rr-maskable-512.png", icon_html(512, scale=.74), 512),
        ("rr-apple-touch-icon.png", icon_html(180, scale=.9), 180),
        ("favicon-32.png", icon_html(32, scale=1.12), 32),
        ("og.png", og_html(), 0),
    ]
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox"])
        with tempfile.TemporaryDirectory() as temp:
            for name, markup, size in jobs:
                width, height = (size, size) if size else (1200, 630)
                source = Path(temp) / (name + ".html")
                source.write_text(markup, encoding="utf-8")
                page = await browser.new_page(viewport={"width": width, "height": height})
                await page.goto(source.as_uri())
                await page.evaluate("document.fonts.ready")
                data = await page.screenshot()
                await page.close()
                if name == "favicon-32.png":
                    (SITE / "favicon.ico").write_bytes(ico(data, 32))
                elif name == "og.png":
                    (SITE / "og.png").write_bytes(data)
                else:
                    (ICONS / name).write_bytes(data)
        await browser.close()
    # El ícono vectorial envuelve el PNG de 512: el dibujo depende de la fuente, que un SVG suelto no puede cargar.
    encoded = base64.b64encode((ICONS / "rr-512.png").read_bytes()).decode("ascii")
    (ICONS / "rr-icon.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><image width="512" height="512" href="data:image/png;base64,{encoded}"/></svg>\n',
        encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(render())
