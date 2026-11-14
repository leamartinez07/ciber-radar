#!/usr/bin/env python3
"""Escribe la nota completa de cada noticia, en español y en inglés, con palabras propias.

Lee el artículo original, se lo pasa a un modelo de IA abierto y guarda en `item["tr"]` una nota que cuenta
todos los hechos (quién, qué, cifras, CVE, versiones, fechas, qué hacer) sin copiar las frases del medio.
De las fuentes con licencia abierta (`reuse` en feeds.toml) hace una traducción fiel, porque su licencia lo permite.
El texto del medio nunca se guarda ni se publica: solo vive en memoria mientras se escribe la nota.

El modelo se usa a través de cualquier servidor compatible con la API de chat de OpenAI: por defecto el
`llama-server` de llama.cpp corriendo en la misma máquina (LLM_URL, LLM_MODEL y LLM_KEY lo cambian).
Solo usa la biblioteca estándar.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import re
import sys
import time
import tomllib
import urllib.request
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect import UTC, fetch_url, month_files, read_json, write_json  # noqa: E402
from enrich import NOTE_DAYS, https, is_removed, read_article, removed_rules  # noqa: E402

log = logging.getLogger("ciber-radar.summarize")

LLM_URL = os.environ.get("LLM_URL", "http://127.0.0.1:8080/v1/chat/completions")
LLM_MODEL = os.environ.get("LLM_MODEL", "local")
SOURCE_MAX_CHARS = 12000      # lo que se le pasa al modelo del artículo original
MIN_SOURCE_CHARS = 300        # con menos que esto no hay de dónde escribir una nota completa
MAX_TRIES = 2
LANG_NAMES = {"es": "español neutro de prensa, claro y sin regionalismos", "en": "English"}

SCHEMA = {
    "type": "object",
    "properties": {code: {
        "type": "object",
        "properties": {"title": {"type": "string"}, "summary": {"type": "string"},
                       "body": {"type": "array", "items": {"type": "string"}}},
        "required": ["title", "summary", "body"]} for code in ("es", "en")},
    "required": ["es", "en"],
}

REWRITE = """Sos el redactor de Ciber Radar, un diario de ciberseguridad. Con el artículo de abajo escribí la nota \
completa, una versión en español y otra en inglés.

Reglas:
- Contá TODO lo que informa el artículo: quién, qué pasó, cómo, cifras, nombres, productos y versiones afectadas, \
CVE, fechas, declaraciones (atribuidas, sin copiar la cita textual larga), contexto y qué tiene que hacer el lector.
- Escribilo con tus propias palabras y tu propio orden. No copies frases del original ni lo traduzcas oración por oración.
- No inventes nada que no esté en el artículo. No opines.
- El cuerpo va en párrafos de 2 a 5 oraciones, entre 5 y 12 párrafos según cuánto diga el artículo.
- title: titular claro, máximo 110 caracteres. summary: bajada de una o dos oraciones.
- Español: {es}. Inglés: natural, de prensa.
- Respondé solo el JSON con las claves es y en, cada una con title, summary y body (lista de párrafos)."""

TRANSLATE = """Sos el traductor de Ciber Radar. El texto de abajo es de una fuente pública cuya licencia permite \
traducirlo y republicarlo. Traducilo completo y fiel, sin resumir ni agregar nada, al español y al inglés \
(si ya está en uno de esos idiomas, esa versión queda corregida y bien redactada).

- Mantené cada párrafo, subtítulo y punto de la lista, en el mismo orden, como un elemento de body.
- Los nombres de productos, CVE, comandos y código quedan como están.
- title: el titular traducido. summary: una o dos oraciones que digan de qué se trata.
- Español: {es}.
- Respondé solo el JSON con las claves es y en, cada una con title, summary y body (lista de párrafos)."""


def chat(messages: list[dict], max_tokens: int = 6000, timeout: float = 900) -> str:
    """Una consulta al servidor de chat; devuelve el texto de la respuesta."""
    payload = {"model": LLM_MODEL, "messages": messages, "temperature": 0.3, "max_tokens": max_tokens,
               "response_format": {"type": "json_schema", "json_schema": {"name": "nota", "schema": SCHEMA}}}
    if LLM_URL.startswith("http://127.0.0.1"):
        payload["chat_template_kwargs"] = {"enable_thinking": False}  # sin razonamiento oculto: más rápido
    headers = {"Content-Type": "application/json"}
    if os.environ.get("LLM_KEY"):
        headers["Authorization"] = "Bearer " + os.environ["LLM_KEY"]
    request = urllib.request.Request(LLM_URL, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())["choices"][0]["message"]["content"]


def clean(text: object, limit: int) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()[:limit] if isinstance(text, str) else ""


def parse(answer: str, min_paragraphs: int) -> dict:
    """Valida la respuesta del modelo; si no sirve, lanza ValueError y la nota se reintenta en otra corrida."""
    answer = re.sub(r"^```(?:json)?|```$", "", answer.strip()).strip()
    data = json.loads(answer)
    out = {}
    for code in ("es", "en"):
        part = data.get(code) or {}
        body = [clean(p, 3000) for p in part.get("body") or []]
        body = [p for p in body if len(p) >= 20][:60]
        title, summary = clean(part.get("title"), 160), clean(part.get("summary"), 400)
        if not title or len(body) < min_paragraphs:
            raise ValueError(f"respuesta incompleta en {code}")
        out[code] = {"title": title, "summary": summary, "body": body}
    return out


def source_text(item: dict, fetch: Callable[[str], bytes]) -> str:
    """Texto del artículo original para dárselo al modelo (no se guarda)."""
    if item.get("body"):
        blocks = item["body"]
    else:
        _, blocks = read_article(fetch(https(item["url"])), item["url"])
    text = "\n\n".join(t for _, t in blocks)
    if len(text) < MIN_SOURCE_CHARS:
        text = item.get("excerpt") or item.get("summary") or ""
    return text[:SOURCE_MAX_CHARS]


def write_note(item: dict, text: str, ask: Callable[[list[dict]], str]) -> dict:
    licensed = bool(item.get("body"))
    rules = (TRANSLATE if licensed else REWRITE).format(es=LANG_NAMES["es"])
    article = f"Medio: {item['source']}\nFecha: {item['published'][:10]}\nTitular: {item['title']}\n\n{text}"
    answer = ask([{"role": "system", "content": rules}, {"role": "user", "content": article}])
    short = len(text) < 1500
    return parse(answer, 1 if short else 3)


def needs_note(item: dict, since: str) -> bool:
    return ("tr" not in item and item.get("tr_tries", 0) < MAX_TRIES and item.get("published", "") >= since
            and "news.google.com" not in item.get("url", "") and item.get("url", "").startswith(("https://", "http://")))


def summarize(config: dict, data_dir: Path, now: dt.datetime, minutes: float = 40, limit: int = 200,
              ask: Callable[[list[dict]], str] | None = None, fetch: Callable[[str], bytes] | None = None,
              clock: Callable[[], float] = time.monotonic) -> dict:
    ask = ask or chat
    fetch = fetch or (lambda url: fetch_url(url, timeout=15, accept="text/html,application/xhtml+xml"))
    rules = removed_rules(config)
    since = (now - dt.timedelta(days=NOTE_DAYS)).isoformat(timespec="seconds")
    months = {path: read_json(path, []) for path in month_files(data_dir)}
    pending = [i for items in months.values() for i in items if needs_note(i, since) and not is_removed(i, rules)]
    pending.sort(key=lambda i: i["published"], reverse=True)
    pending.sort(key=lambda i: not i.get("alert"))  # primero las alertas, después las más nuevas
    deadline = clock() + minutes * 60
    done = failed = 0

    def save() -> None:
        for path, items in months.items():
            write_json(path, items)
        by_id = {i["id"]: i for items in months.values() for i in items}
        latest_path = data_dir / "latest.json"
        latest = read_json(latest_path, None)
        if latest:
            latest["items"] = [by_id.get(i["id"], i) for i in latest["items"]]
            write_json(latest_path, latest)

    for item in pending[:limit]:
        if clock() > deadline:
            break
        try:
            text = source_text(item, fetch)
            if not text:
                raise ValueError("sin texto")
            item["tr"] = write_note(item, text, ask)
            item.pop("tr_tries", None)
            done += 1
        except Exception as exc:  # una nota que falla no frena las demás
            item["tr_tries"] = item.get("tr_tries", 0) + 1
            failed += 1
            log.warning("%s: %s %s", item["id"], type(exc).__name__, exc)
        save()  # se guarda nota por nota: si la corrida se corta, no se pierde lo hecho
    left = sum(1 for i in pending if "tr" not in i and i.get("tr_tries", 0) < MAX_TRIES)
    return {"written": done, "failed": failed, "left": left}


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=root / "feeds.toml")
    parser.add_argument("--data", type=Path, default=root / "data")
    parser.add_argument("--minutes", type=float, default=40)
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = tomllib.loads(args.config.read_text(encoding="utf-8"))
    report = summarize(config, args.data, dt.datetime.now(UTC), minutes=args.minutes, limit=args.limit)
    log.info("escritas=%d fallidas=%d pendientes=%d", report["written"], report["failed"], report["left"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
