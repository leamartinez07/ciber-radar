#!/usr/bin/env python3
"""Genera la marca de Ciber Radar desde un solo dibujo: íconos de la app, favicon e imagen para redes.

El emblema es un radar: dos anillos, un barrido con el degradado de la marca LM y un punto rojo
que marca la amenaza detectada. Es el mismo que aparece en la cabecera del sitio.

Herramienta de desarrollo: usa Playwright con Chromium para pasar el SVG a PNG.
    PLAYWRIGHT_BROWSERS_PATH=… python tools/make_brand.py
"""
from __future__ import annotations

import asyncio
import struct
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
ICONS = SITE / "icons"

INK, PAPER, LILAC, RED = "#16131d", "#f3f0f8", "#b9a1ff", "#ff7586"
BEAM = '<linearGradient id="beam" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#76cee2"/><stop offset=".5" stop-color="#ef86d3"/><stop offset="1" stop-color="#8f5cff"/></linearGradient>'


def radar(scale: float = 1.0) -> str:
    """El emblema en una caja de 512, centrado. scale achica el dibujo para la zona segura."""
    s = scale
    c = 256
    outer, inner = 176 * s, 100 * s
    end_x, end_y = c + outer * 0.866, c - outer * 0.5
    return (
        f'<g fill="none" stroke="{LILAC}" stroke-width="{22 * s:.1f}"><circle cx="{c}" cy="{c}" r="{outer:.1f}"/>'
        f'<circle cx="{c}" cy="{c}" r="{inner:.1f}"/></g>'
        f'<path d="M{c} {c} L{c} {c - outer:.1f} A{outer:.1f} {outer:.1f} 0 0 1 {end_x:.1f} {end_y:.1f} Z" fill="url(#beam)"/>'
        f'<circle cx="{c}" cy="{c}" r="{26 * s:.1f}" fill="{PAPER}"/>'
        f'<circle cx="{c + 76 * s:.1f}" cy="{c + 72 * s:.1f}" r="{24 * s:.1f}" fill="{RED}"/>'
    )


def icon_svg(rounded: bool, scale: float = 1.0) -> str:
    corner = ' rx="112"' if rounded else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><defs>{BEAM}</defs>'
            f'<rect width="512" height="512"{corner} fill="{INK}"/>{radar(scale)}</svg>')


def og_html() -> str:
    fonts = (SITE / "fonts").resolve().as_uri()
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: "Inter Tight"; src: url("{fonts}/inter-tight-latin-wght-normal.woff2"); font-weight: 100 900; }}
@font-face {{ font-family: "Source Serif"; src: url("{fonts}/source-serif-4-latin-400-italic.woff2"); font-style: italic; }}
@font-face {{ font-family: "Manrope"; src: url("{fonts}/manrope-latin-wght-normal.woff2"); font-weight: 200 800; }}
html, body {{ margin: 0; width: 1200px; height: 630px; overflow: hidden; }}
body {{ display: grid; place-items: center; background: radial-gradient(circle at 50% 38%, #221a35, #0d0b12 62%); color: {PAPER}; font-family: "Inter Tight"; }}
.wrap {{ display: flex; flex-direction: column; align-items: center; }}
svg {{ width: 200px; height: 200px; }}
h1 {{ margin: 18px 0 0; font-weight: 800; font-size: 104px; line-height: 1; letter-spacing: -.045em; }}
p {{ margin: 18px 0 0; font: italic 32px/1.2 "Source Serif"; color: #cdc6d8; }}
.beam {{ width: 220px; height: 5px; margin-top: 26px; border-radius: 3px; background: linear-gradient(90deg, #76cee2, #ef86d3, #8f5cff); }}
small {{ margin-top: 18px; font: 600 20px/1 "Manrope"; letter-spacing: .14em; color: #a49db2; }}
</style></head><body><div class="wrap">
<svg viewBox="0 0 512 512"><defs>{BEAM}</defs>{radar()}</svg>
<h1>Ciber Radar</h1><p>Toda la ciberseguridad, a medida que sale.</p><div class="beam"></div>
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
        ("favicon-32.png", icon_svg(True), 32),
    ]
    async with async_playwright() as p:
        browser = await p.chromium.launch()
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
