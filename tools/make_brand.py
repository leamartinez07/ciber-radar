"""Genera la marca de Ciber Radar desde un solo dibujo: íconos de la app, favicon e imagen para redes.

El emblema es la R que une CIBE y ADAR: la panza es la pantalla del radar (hueco, punto y barrido)
y la pata son las ondas que emite. Es de un solo color: blanco sobre negro en la versión principal.
Es la misma letra que aparece en la cabecera del sitio.

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

BLACK, WHITE, GREY = "#0a0a0a", "#ffffff", "#a3a3aa"
CX, CY, OUTER, HOLE, WIDTH = 55, 31, 31, 20, 102  # la R en una caja de 102 × 100
BODY = "M0 0H55A31 31 0 0 1 55 62H22V100H0ZM35 31A20 20 0 1 0 75 31A20 20 0 1 0 35 31Z"
SWEEP = "M55 31L55 11A20 20 0 0 1 75 31Z"


def wave(radius: float) -> str:
    pt = lambda a: (CX + radius * math.cos(math.radians(a)), CY + radius * math.sin(math.radians(a)))
    (x0, y0), (x1, y1) = pt(44), pt(96)
    return f"M{x0:.1f} {y0:.1f}A{radius} {radius} 0 0 1 {x1:.1f} {y1:.1f}"


def radar(height: float, cx: float, cy: float, color: str = WHITE, waves: tuple[float, ...] = (43, 59, 75),
          stroke: float = 12.0, sweep: bool = True) -> str:
    """La R de la marca, de alto height y centrada en (cx, cy)."""
    width = height * WIDTH / 100
    beam = f'<path d="{SWEEP}" fill="{color}" opacity=".5"/>' if sweep else ""
    return (f'<svg x="{cx - width / 2:.1f}" y="{cy - height / 2:.1f}" width="{width:.1f}" height="{height:.1f}" '
            f'viewBox="0 0 {WIDTH} 100"><clipPath id="leg"><rect x="30" y="0" width="{WIDTH - 30}" height="100"/></clipPath>'
            f'<path fill-rule="evenodd" fill="{color}" d="{BODY}"/>{beam}<circle cx="{CX}" cy="{CY}" r="6" fill="{color}"/>'
            f'<g clip-path="url(#leg)" fill="none" stroke="{color}" stroke-width="{stroke}">'
            f'{"".join(f'<path d="{wave(r)}"/>' for r in waves)}</g></svg>')


def icon_svg(rounded: bool, scale: float = 1.0, small: bool = False) -> str:
    corner = ' rx="112"' if rounded else ""
    # En 32 px tres ondas se empastan: el favicon lleva dos, más gruesas, y sin barrido.
    mark = radar(380, 256, 256, waves=(45, 66), stroke=17.0, sweep=False) if small else radar(300 * scale, 256, 256)
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
h1 svg {{ width: auto; height: .692em; margin: 0 .03em 0 .05em; }}
h1 span {{ font-weight: 250; }}
p {{ margin: 30px 0 0; font: 500 30px/1.2 "Archivo"; color: #ffffff; }}
small {{ margin-top: 26px; font: 600 19px/1 "Archivo"; letter-spacing: .2em; color: {GREY}; }}
</style></head><body>
<svg class="echo" viewBox="0 0 1200 630"><g fill="none" stroke="{WHITE}" stroke-width="2">
{"".join(f'<circle cx="600" cy="315" r="{r}"/>' for r in range(150, 760, 105))}</g></svg>
<div class="wrap"><h1><span>CIBE</span><svg viewBox="0 0 {WIDTH} 100">{radar(100, WIDTH / 2, 50)}</svg>ADAR</h1>
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
