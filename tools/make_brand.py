"""Genera la marca de Ciber Radar desde un solo dibujo: íconos de la app, favicon e imagen para redes.

El emblema es la C de la marca hecha con tres anillos de radar, abiertos hacia el punto que marca
la señal detectada. Es de un solo color: blanco sobre negro en la versión principal. Es el mismo
dibujo que abre la palabra CIBERRADAR en la cabecera del sitio.

Herramienta de desarrollo: usa Playwright con Chromium para pasar el SVG a PNG.
    PLAYWRIGHT_BROWSERS_PATH=… python tools/make_brand.py
"""
from __future__ import annotations

import asyncio
import math
import struct
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
ICONS = SITE / "icons"

BLACK, WHITE, GREY, RED = "#0a0a0a", "#ffffff", "#a3a3aa", "#e2001a"
RINGS, OPENING = (45.5, 30.0, 14.5), 36  # radios sobre una caja de 100 y media apertura en grados


def radar(size: float, cx: float, cy: float, color: str = WHITE, rings: tuple[float, ...] = RINGS,
          stroke: float = 9.0) -> str:
    """El emblema dibujado en un cuadrado de lado size con centro en (cx, cy)."""
    k = size / 100
    dx, dy = math.cos(math.radians(OPENING)), math.sin(math.radians(OPENING))
    arcs = "".join(
        f'<path d="M{cx + r * k * dx:.1f} {cy - r * k * dy:.1f}A{r * k:.1f} {r * k:.1f} 0 1 0 '
        f'{cx + r * k * dx:.1f} {cy + r * k * dy:.1f}"/>' for r in rings)
    return (f'<g fill="none" stroke="{color}" stroke-width="{stroke * k:.1f}">{arcs}</g>'
            f'<circle cx="{cx + 36 * k:.1f}" cy="{cy:.1f}" r="{7 * k:.1f}" fill="{RED}"/>')


def icon_svg(rounded: bool, scale: float = 1.0, small: bool = False) -> str:
    corner = ' rx="112"' if rounded else ""
    # En 32 px tres anillos se empastan: el favicon lleva dos, más gruesos.
    mark = radar(400, 256, 256, rings=(43.0, 20.0), stroke=14.0) if small else radar(330 * scale, 256, 256)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
            f'<rect width="512" height="512"{corner} fill="{BLACK}"/>{mark}</svg>')


def og_html() -> str:
    fonts = (SITE / "fonts").resolve().as_uri()
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: "Archivo"; src: url("{fonts}/archivo-latin-wdth-normal.woff2"); font-weight: 100 900; font-stretch: 62% 125%; }}
html, body {{ margin: 0; width: 1200px; height: 630px; overflow: hidden; }}
body {{ display: grid; place-items: center; background: {BLACK}; color: {WHITE}; font-family: "Archivo"; }}
.echo {{ position: absolute; inset: 0; width: 1200px; height: 630px; opacity: .09; }}
.wrap {{ position: relative; display: flex; flex-direction: column; align-items: center; }}
h1 {{ display: flex; align-items: baseline; margin: 0; font-weight: 850; font-stretch: 92%; font-size: 138px; line-height: 1; letter-spacing: -.015em; }}
h1 svg {{ width: .727em; height: .727em; margin-right: .035em; }}
h1 span {{ font-weight: 250; }}
p {{ margin: 30px 0 0; font: 500 30px/1.2 "Archivo"; color: #ffffff; }}
small {{ margin-top: 26px; font: 600 19px/1 "Archivo"; letter-spacing: .2em; color: {GREY}; }}
</style></head><body>
<svg class="echo" viewBox="0 0 1200 630"><g fill="none" stroke="{WHITE}" stroke-width="2">
{"".join(f'<circle cx="600" cy="315" r="{r}"/>' for r in range(150, 760, 105))}</g></svg>
<div class="wrap"><h1><svg viewBox="0 0 100 100">{radar(100, 50, 50)}</svg><span>IBER</span>RADAR</h1>
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
