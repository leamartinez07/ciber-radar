#!/usr/bin/env python3
"""Completa cada nota con lo que hace falta para leerla dentro del sitio.

- La imagen principal que el medio eligió para compartirla (og:image), salvo las de relleno.
- El texto completo, solo de las fuentes cuya licencia permite republicarlo (campo `reuse` en feeds.toml).

Nunca se republica el artículo de un medio privado: de esos queda el extracto de su feed y, más adelante,
un resumen propio. Todo lo que llega de una página se trata como dato no confiable y sale como texto plano.
Solo usa la biblioteca estándar.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import html
import json
import logging
import re
import sys
import tomllib
import urllib.parse
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect import UTC, fetch_url, month_files, read_json, safe_url, write_json  # noqa: E402

log = logging.getLogger("ciber-radar.enrich")

NOTE_DAYS = 45            # mismas notas que tienen página propia en el sitio
PER_RUN = 120             # tope de páginas a leer por corrida; el resto queda para la próxima
BODY_MAX_CHARS = 14000
BODY_MAX_PARAGRAPHS = 60
PARAGRAPH_MIN = 40
# Imágenes de relleno: logos, la portada genérica del medio o la ilustración de una categoría.
GENERIC_IMAGE = re.compile(
    r"(logo|default|placeholder|preview[_-]?image|fallback|og[_-]?image|share[_-]?image|"
    r"category|cybersecurity-news|site[_-]?image|social[_-]?card|brand)", re.I)
# Frases del pie de página o de encuestas que algunos sitios ponen dentro del cuerpo.
BOILERPLATE = re.compile(
    r"(share your thoughts|product survey|provided subject to this notification|privacy (&|and) use policy|"
    r"subscribe to (our|the) newsletter|follow us on|cookie)", re.I)
BLOCK_TAGS = {"p", "li", "h2", "h3", "h4", "blockquote", "pre"}
SKIP_TAGS = {"script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg", "figure", "button"}


def https(url: str) -> str:
    """Las fuentes con http también sirven https; nunca se lee una página sin cifrar."""
    return "https://" + url[len("http://"):] if url.startswith("http://") else url


class Article(HTMLParser):
    """Saca de una página la imagen para compartir y los párrafos del cuerpo, como texto plano."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.blocks: list[tuple[bool, str, str]] = []  # (dentro de <article> o <main>, etiqueta, texto)
        self.depth_article = 0
        self.depth_skip = 0
        self.current: list[str] | None = None
        self.current_tag = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {k: v or "" for k, v in attrs}
        if tag == "meta":
            key = (values.get("property") or values.get("name") or "").lower()
            if key in ("og:image", "og:image:url", "og:image:secure_url", "twitter:image") and key not in self.meta:
                self.meta[key] = values.get("content", "")
            return
        if tag in ("article", "main"):
            self.depth_article += 1
        elif tag in SKIP_TAGS:
            self.depth_skip += 1
        elif tag in BLOCK_TAGS and not self.depth_skip and self.current is None:
            self.current, self.current_tag = [], tag
        elif tag == "br" and self.current is not None:
            self.current.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("article", "main") and self.depth_article:
            self.depth_article -= 1
        elif tag in SKIP_TAGS and self.depth_skip:
            self.depth_skip -= 1
        elif tag == self.current_tag and self.current is not None:
            text = re.sub(r"\s+", " ", "".join(self.current)).strip()
            if text:
                self.blocks.append((self.depth_article > 0, tag, text))
            self.current, self.current_tag = None, ""

    def handle_data(self, data: str) -> None:
        if self.current is not None and not self.depth_skip:
            self.current.append(data)

    def image(self, base: str) -> str:
        for key in ("og:image:secure_url", "og:image", "og:image:url", "twitter:image"):
            raw = html.unescape(self.meta.get(key, "")).strip()
            if raw:
                url = safe_url(https(urllib.parse.urljoin(base, raw)))
                if url.startswith("https://"):
                    return url
        return ""

    def paragraphs(self) -> list[list[str]]:
        """Bloques como [tipo, texto]: "h" subtítulo, "li" ítem de lista, "p" párrafo."""
        inside = [b for b in self.blocks if b[0]]
        chosen = inside if sum(len(t) for _, _, t in inside) >= 400 else self.blocks
        out: list[list[str]] = []
        total = 0
        for _, tag, text in chosen:
            kind = "h" if tag in ("h2", "h3", "h4") else "li" if tag == "li" else "p"
            if (len(text) < PARAGRAPH_MIN and kind == "p") or BOILERPLATE.search(text):
                continue
            if out and text == out[-1][1]:
                continue
            out.append([kind, text])
            total += len(text)
            if total >= BODY_MAX_CHARS or len(out) >= BODY_MAX_PARAGRAPHS:
                break
        return out


def read_article(page: bytes, url: str) -> tuple[str, list[list[str]]]:
    parser = Article()
    parser.feed(page.decode("utf-8", "replace"))
    parser.close()
    return parser.image(url), parser.paragraphs()


def is_generic(url: str) -> bool:
    return bool(GENERIC_IMAGE.search(urllib.parse.urlsplit(url).path))


def removed_rules(config: dict) -> dict[str, set[str]]:
    """Notas o fuentes retiradas a pedido: se quitan del sitio en la próxima edición."""
    block = config.get("removed", {})
    return {"ids": set(block.get("ids", [])), "urls": {u.rstrip("/") for u in block.get("urls", [])},
            "sources": set(block.get("sources", [])), "domains": {d.lower().removeprefix("www.") for d in block.get("domains", [])}}


def is_removed(item: dict, rules: dict[str, set[str]]) -> bool:
    host = (urllib.parse.urlsplit(item.get("url", "")).hostname or "").lower().removeprefix("www.")
    return (item.get("id") in rules["ids"] or item.get("url", "").rstrip("/") in rules["urls"]
            or item.get("source") in rules["sources"]
            or any(host == d or host.endswith("." + d) for d in rules["domains"]))


def needs_work(item: dict, since: str) -> bool:
    url = item.get("url", "")
    return ("enriched" not in item and item.get("published", "") >= since
            and url.startswith(("https://", "http://")) and "news.google.com" not in url)


def enrich(config: dict, data_dir: Path, now: dt.datetime,
           fetch: Callable[[str], bytes] | None = None, limit: int = PER_RUN) -> dict:
    fetch = fetch or (lambda url: fetch_url(url, timeout=12, accept="text/html,application/xhtml+xml"))
    reuse = {f["name"]: f["reuse"] for f in config["feeds"] if f.get("reuse")}
    rules = removed_rules(config)
    since = (now - dt.timedelta(days=NOTE_DAYS)).isoformat(timespec="seconds")
    stamp = now.isoformat(timespec="seconds")

    months = {path: read_json(path, []) for path in month_files(data_dir)}
    purged = 0
    for path, items in months.items():
        kept = [i for i in items if not is_removed(i, rules)]
        purged += len(items) - len(kept)
        months[path] = kept

    pending = [i for items in months.values() for i in items if needs_work(i, since)]
    pending.sort(key=lambda i: i["published"], reverse=True)
    batch = pending[:limit]

    def work(item: dict) -> tuple[dict, str, list[list[str]], str]:
        try:
            image, paragraphs = read_article(fetch(https(item["url"])), item["url"])
            return item, image, paragraphs, ""
        except Exception as exc:  # una página caída no frena las demás
            return item, "", [], type(exc).__name__

    failed = 0
    with cf.ThreadPoolExecutor(max_workers=10) as pool:
        for item, image, paragraphs, error in pool.map(work, batch):
            item["enriched"] = stamp
            failed += bool(error)
            if image and not is_generic(image):
                item["image"] = image
            if item["source"] in reuse and paragraphs:
                item["body"] = paragraphs
                item["reuse"] = reuse[item["source"]]

    # Una misma imagen en varias notas de un medio es su portada genérica: no ilustra ninguna.
    counts = Counter((i["source"], i["image"]) for items in months.values() for i in items if i.get("image"))
    for items in months.values():
        for i in items:
            if i.get("image") and counts[(i["source"], i["image"])] > 1:
                del i["image"]

    for path, items in months.items():
        write_json(path, items)
    by_id = {i["id"]: i for items in months.values() for i in items}
    latest_path = data_dir / "latest.json"
    latest = read_json(latest_path, None)
    if latest:
        latest["items"] = [by_id.get(i["id"], i) for i in latest["items"] if not is_removed(i, rules)]
        write_json(latest_path, latest)
    return {"read": len(batch), "failed": failed, "left": len(pending) - len(batch), "purged": purged}


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=root / "feeds.toml")
    parser.add_argument("--data", type=Path, default=root / "data")
    parser.add_argument("--limit", type=int, default=PER_RUN)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = tomllib.loads(args.config.read_text(encoding="utf-8"))
    report = enrich(config, args.data, dt.datetime.now(UTC), limit=args.limit)
    log.info("leidas=%d fallidas=%d pendientes=%d retiradas=%d", report["read"], report["failed"], report["left"], report["purged"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
