#!/usr/bin/env python3
"""Genera los íconos de la app, el favicon y la imagen para redes de Ciber Radar.

La marca es tipográfica: las dos R del medio espalda con espalda (la de CIBER, espejada), en Hubot Sans
900 y en rojo, con el alto exacto de CIBE y ADAR; estos van en Mona Sans entre dos filetes. Los íconos
llevan solo las dos R.

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
    return (f'@font-face {{ font-family: "Mona"; src: url("{fonts}/mona-sans-latin-wght-normal.woff2"); font-weight: 200 900; }}'
            f'@font-face {{ font-family: "Hubot"; src: url("{fonts}/hubot-sans-latin-900-normal.woff2"); font-weight: 900; }}')


def icon_html(size: int, scale: float = 1.0, rules: bool = True) -> str:
    """Las dos R espalda con espalda entre dos filetes. scale achica el dibujo para la zona segura."""
    unit = size * scale
    rule = f"border-block: {max(1, round(unit * .028))}px solid {INK}; padding: {unit * .035:.1f}px 0 {unit * .012:.1f}px;" if rules else ""
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>{fonts_css()}
html, body {{ margin: 0; width: {size}px; height: {size}px; overflow: hidden; }}
body {{ display: grid; place-items: center; background: {PAPER}; color: {INK}; }}
b {{ display: flex; font: 900 {unit * (.6 if rules else .86):.1f}px/.735 "Hubot"; color: {RED}; {rule} }}
i, u {{ font-style: normal; text-decoration: none; display: block; translate: 0 -.0175em; }}
i {{ transform: scaleX(-1); }}
</style></head><body><b><i>R</i><u>R</u></b></body></html>'''


def og_html() -> str:
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>{fonts_css()}
html, body {{ margin: 0; width: 1200px; height: 630px; overflow: hidden; }}
body {{ display: grid; place-items: center; background: {PAPER}; color: {INK}; }}
.plate {{ display: flex; flex-direction: column; align-items: center; }}
h1 {{ display: flex; align-items: center; gap: .17em; margin: 0; font: 850 118px/.92 "Mona"; letter-spacing: -.012em; white-space: nowrap; }}
h1 .side {{ display: block; height: 1.18em; padding: .08em .05em .03em; border-block: .085em solid {INK}; line-height: .9; }}
h1 .rr {{ display: flex; height: .735em; font: 900 1.6054em/.735 "Hubot"; color: {RED}; }}
h1 .rr i, h1 .rr u {{ font-style: normal; text-decoration: none; display: block; translate: 0 -.0175em; }}
h1 .rr i {{ transform: scaleX(-1); }}
p {{ margin: 36px 0 0; font: 480 30px/1.2 "Mona"; color: {GREY}; white-space: nowrap; }}
</style></head><body><div class="plate"><h1><span class="side">CIBE</span><span class="rr"><i>R</i><u>R</u></span><span class="side">ADAR</span></h1>
<p>Noticias de ciberseguridad de Argentina, Latinoamérica y el mundo</p></div></body></html>'''


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
