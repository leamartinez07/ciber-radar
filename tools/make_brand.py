#!/usr/bin/env python3
"""Genera la marca de Ciber Radar desde un solo dibujo: íconos de la app, favicon e imagen para redes.

El emblema es una R dibujada a medida: la panza es el visor de un radar, con la señal detectada en
el centro, y la pata es el haz que sale del visor. En la marca completa va grande y al centro, con
CIBE y ADAR a los lados entre dos filetes. El dibujo vive en collector/render.py (r_mark).

Herramienta de desarrollo: usa Playwright con Chromium para pasar el SVG a PNG.
    PLAYWRIGHT_BROWSERS_PATH=… python tools/make_brand.py
"""
from __future__ import annotations

import asyncio
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
ICONS = SITE / "icons"
sys.path.insert(0, str(ROOT / "collector"))
from render import R_WIDTH, r_mark  # noqa: E402

BLUE, WHITE, YELLOW, SOFT = "#1a3cff", "#ffffff", "#ffe14d", "#d5dcff"


def icon_svg(rounded: bool, scale: float = 1.0, small: bool = False) -> str:
    """La R blanca con la señal amarilla sobre el azul de marca."""
    corner = ' rx="112"' if rounded else ""
    height = (360 if small else 300) * scale
    width = height * R_WIDTH / 100
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect width="512" height="512"{corner} fill="{BLUE}"/>'
            f'<svg x="{256 - width / 2 + height * .03:.1f}" y="{256 - height / 2:.1f}" width="{width:.1f}" height="{height:.1f}" '
            f'viewBox="0 0 {R_WIDTH} 100">{r_mark(WHITE, YELLOW)}</svg></svg>')


def og_html() -> str:
    fonts = (SITE / "fonts").resolve().as_uri()
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: "Archivo"; src: url("{fonts}/archivo-latin-wdth-normal.woff2"); font-weight: 100 900; font-stretch: 62% 125%; }}
html, body {{ margin: 0; width: 1200px; height: 630px; overflow: hidden; }}
body {{ display: grid; place-items: center; background: {BLUE}; color: {WHITE}; font-family: "Archivo"; }}
.wrap {{ display: flex; flex-direction: column; align-items: center; }}
h1 {{ display: flex; align-items: stretch; gap: .22em; margin: 0; font-weight: 900; font-stretch: 118%; font-size: 92px; line-height: 1; letter-spacing: .04em; }}
h1 span {{ display: flex; align-items: center; padding: 0 .1em; border-block: .09em solid; }}
h1 svg {{ width: auto; height: 2.1em; }}
p {{ margin: 44px 0 0; font: 600 32px/1.2 "Archivo"; }}
small {{ margin-top: 22px; font: 700 19px/1 "Archivo"; letter-spacing: .2em; color: {SOFT}; }}
</style></head><body>
<div class="wrap"><h1><span>CIBE</span><svg viewBox="0 0 {R_WIDTH} 100">{r_mark(WHITE, YELLOW)}</svg><span>ADAR</span></h1>
<p>Toda la ciberseguridad, a medida que sale.</p>
<small>ARGENTINA · LATAM · WORLD</small></div></body></html>'''


def ico(png: bytes, size: int) -> bytes:
    """Un .ico con un PNG adentro, formato que leen todos los navegadores actuales."""
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(png), 6 + 16)
    return header + entry + png


async def render() -> None:
    from playwright.async_api import async_playwright

    ICONS.mkdir(parents=True, exist_ok=True)
    (ICONS / "icon.svg").write_text(icon_svg(rounded=True) + "\n", encoding="utf-8")
    jobs = [
        ("icon-192.png", icon_svg(False), 192),
        ("icon-512.png", icon_svg(False), 512),
        ("icon-maskable-512.png", icon_svg(False, scale=0.82), 512),
        ("apple-touch-icon.png", icon_svg(False, scale=0.9), 180),
        ("favicon-32.png", icon_svg(True, small=True), 32),
    ]
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox"])
        with tempfile.TemporaryDirectory() as temp:
            for name, svg, size in jobs:
                page = await browser.new_page(viewport={"width": size, "height": size})
                await page.set_content(f'<html><body style="margin:0;background:transparent">'
                                       f'{svg.replace("<svg ", f"<svg width={size} height={size} ", 1)}</body></html>')
                data = await page.screenshot(omit_background=True)
                await page.close()
                if name == "favicon-32.png":
                    (SITE / "favicon.ico").write_bytes(ico(data, 32))
                else:
                    (ICONS / name).write_bytes(data)
            og = Path(temp) / "og.html"
            og.write_text(og_html(), encoding="utf-8")
            page = await browser.new_page(viewport={"width": 1200, "height": 630})
            await page.goto(og.as_uri())
            await page.evaluate("document.fonts.ready")
            await page.screenshot(path=str(SITE / "og.png"))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(render())
