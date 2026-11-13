#!/usr/bin/env python3
"""Genera la marca de Ciber Radar desde un solo dibujo: íconos de la app, favicon e imagen para redes.

El emblema es una R de tres líneas paralelas del mismo grosor: recorren el asta, la panza y la pata.
En la panza son los anillos de un radar, con la señal detectada en el centro. El dibujo vive en
collector/render.py (r_mark) y es el mismo de la cabecera del sitio.

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
from render import r_mark  # noqa: E402

NAVY, PAPER, ORANGE, YELLOW, MUTED = "#14233f", "#f3ead7", "#e2491f", "#f2b632", "#a9b4c8"
LINES = (ORANGE, YELLOW, PAPER)


def mark(size: float, cx: float, cy: float, small: bool = False) -> str:
    """La R en un cuadrado de lado size con centro en (cx, cy). En chico lleva dos líneas más gruesas."""
    art = r_mark((ORANGE, PAPER), ORANGE, stroke=12, gap=6, uid="s") if small else r_mark(LINES, ORANGE, uid="m")
    return f'<svg x="{cx - size / 2:.1f}" y="{cy - size / 2:.1f}" width="{size:.1f}" height="{size:.1f}" viewBox="0 0 100 100">{art}</svg>'


def icon_svg(rounded: bool, scale: float = 1.0, small: bool = False) -> str:
    corner = ' rx="112"' if rounded else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
            f'<rect width="512" height="512"{corner} fill="{NAVY}"/>{mark((400 if small else 340) * scale, 262, 256, small)}</svg>')


def og_html() -> str:
    fonts = (SITE / "fonts").resolve().as_uri()
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: "Archivo"; src: url("{fonts}/archivo-latin-wdth-normal.woff2"); font-weight: 100 900; font-stretch: 62% 125%; }}
html, body {{ margin: 0; width: 1200px; height: 630px; overflow: hidden; }}
body {{ display: grid; place-items: center; background: {NAVY}; color: {PAPER}; font-family: "Archivo"; }}
.wrap {{ display: flex; flex-direction: column; align-items: center; margin-top: -14px; }}
h1 {{ display: flex; align-items: center; gap: .2em; margin: 0; font-weight: 850; font-stretch: 108%; font-size: 116px; line-height: 1; letter-spacing: .01em; }}
h1 svg {{ width: 1.02em; height: 1.02em; }}
h1 b {{ color: {ORANGE}; }}
p {{ margin: 34px 0 0; font: 500 31px/1.2 "Archivo"; }}
small {{ margin-top: 22px; font: 700 19px/1 "Archivo"; letter-spacing: .2em; color: {MUTED}; }}
.rule {{ position: absolute; left: 0; right: 0; bottom: 0; height: 28px; background: linear-gradient({ORANGE} 50%, {YELLOW} 50%); }}
</style></head><body>
<div class="wrap"><h1><svg viewBox="0 0 100 100">{r_mark(LINES, ORANGE, uid="o")}</svg><span>CIBE<b>R</b>ADAR</span></h1>
<p>Toda la ciberseguridad, a medida que sale.</p>
<small>ARGENTINA · LATAM · WORLD</small></div><div class="rule"></div></body></html>'''


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
