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
    return (f'@font-face {{ font-family: "Archivo"; src: url("{fonts}/archivo-latin-wdth-normal.woff2"); font-weight: 100 900; font-stretch: 62% 125%; }}'
            f'@font-face {{ font-family: "Source Serif"; src: url("{fonts}/source-serif-4-latin-600-normal.woff2"); font-weight: 600; }}')


def icon_html(size: int, scale: float = 1.0, rules: bool = True) -> str:
    """Las dos R espalda con espalda entre dos filetes. scale achica el dibujo para la zona segura."""
    unit = size * scale
    rule = f"border-block: {max(1, round(unit * .028))}px solid {INK}; padding: {unit * .035:.1f}px 0 {unit * .012:.1f}px;" if rules else ""
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>{fonts_css()}
html, body {{ margin: 0; width: {size}px; height: {size}px; overflow: hidden; }}
body {{ display: grid; place-items: center; background: {PAPER}; color: {INK}; }}
b {{ display: flex; font: 800 {unit * (.62 if rules else .9):.1f}px/.82 "Archivo"; font-stretch: 62%; color: {RED}; {rule} }}
i {{ font-style: normal; display: block; transform: scaleX(-1); margin-right: -.052em; }}
</style></head><body><b><i>R</i>R</b></body></html>'''


def og_html() -> str:
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>{fonts_css()}
html, body {{ margin: 0; width: 1200px; height: 630px; overflow: hidden; }}
body {{ display: grid; place-items: center; background: {PAPER}; color: {INK}; }}
.plate {{ display: flex; flex-direction: column; align-items: center; }}
h1 {{ display: flex; align-items: center; margin: 0; font: 800 150px/.92 "Archivo"; font-stretch: 62%; white-space: nowrap; }}
h1 .side {{ display: block; padding: .07em .04em .01em; border-block: .085em solid {INK}; line-height: .86; }}
h1 .rr {{ display: flex; margin: 0 .05em; font-size: 1.62em; line-height: .735; color: {RED}; }}
h1 .rr i {{ font-style: normal; display: block; transform: scaleX(-1); margin-right: -.052em; }}
p {{ margin: 34px 0 0; font: 700 27px/1.2 "Archivo"; font-stretch: 80%; letter-spacing: .03em; color: {INK}; white-space: nowrap; }}
</style></head><body><div class="plate"><h1><span class="side">CIBE</span><span class="rr"><i>R</i>R</span><span class="side">ADAR</span></h1>
<p>NOTICIAS DE CIBERSEGURIDAD · ARGENTINA, LATINOAMÉRICA Y EL MUNDO</p></div></body></html>'''


def ico(png: bytes, size: int) -> bytes:
    """Un .ico con un PNG adentro, formato que leen todos los navegadores actuales."""
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(png), 6 + 16)
    return header + entry + png


async def render() -> None:
    from playwright.async_api import async_playwright

    ICONS.mkdir(parents=True, exist_ok=True)
    jobs = [
        ("icon-192.png", icon_html(192), 192),
        ("icon-512.png", icon_html(512), 512),
        ("icon-maskable-512.png", icon_html(512, scale=.74), 512),
        ("apple-touch-icon.png", icon_html(180, scale=.9), 180),
        ("favicon-32.png", icon_html(32, rules=False), 32),
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
    encoded = base64.b64encode((ICONS / "icon-512.png").read_bytes()).decode("ascii")
    (ICONS / "icon.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><image width="512" height="512" href="data:image/png;base64,{encoded}"/></svg>\n',
        encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(render())
