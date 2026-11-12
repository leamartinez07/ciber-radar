#!/usr/bin/env python3
"""Recolecta noticias de ciberseguridad, arma los datos de la app y manda avisos.

Solo usa la biblioteca estándar, así que corre sin instalar nada.
Todo lo que viene de un feed se trata como dato no confiable.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import email.utils
import hashlib
import html
import json
import logging
import os
import re
import sys
import tomllib
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable

log = logging.getLogger("ciber-radar")

USER_AGENT = "Mozilla/5.0 (compatible; CiberRadar/1.0; lector de RSS)"
MAX_FEED_BYTES = 12 * 1024 * 1024
TITLE_MAX = 240
SUMMARY_MAX = 240
TRACKING_PARAMS = ("utm_", "fbclid", "gclid", "mc_cid", "mc_eid")
MIN_HEALTHY_RATIO = 0.5
SAME_STORY_RATIO = 0.5
UTC = dt.timezone.utc


def norm(text: str) -> str:
    """Minúsculas y sin acentos, para comparar textos."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def clean_text(raw: str | None) -> str:
    """Pasa HTML de un feed a texto plano."""
    if not raw:
        return ""
    text = html.unescape(raw)
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,.;:") + "…"


def safe_url(url: str | None) -> str:
    """Devuelve la URL solo si es http(s) y tiene host."""
    if not url:
        return ""
    url = url.strip()
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return ""
    return url if parts.scheme in ("http", "https") and parts.netloc else ""


def canonical_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    query = [
        (k, v)
        for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith(TRACKING_PARAMS)
    ]
    path = parts.path.rstrip("/")
    return urllib.parse.urlunsplit(("https", parts.netloc.lower(), path, urllib.parse.urlencode(query), ""))


def title_key(title: str) -> str:
    """Clave para detectar la misma nota en dos fuentes. Vacía si el título es muy corto."""
    tokens = re.findall(r"[a-z0-9]+", norm(title))
    return " ".join(tokens[:14]) if len(tokens) >= 4 else ""


def title_words(title: str) -> list[str]:
    return sorted(set(re.findall(r"[a-z0-9]{4,}", norm(title))))


def same_story(a: list[str], b: list[str]) -> bool:
    """Dos títulos con la mitad de las palabras en común cuentan como el mismo hecho."""
    first, second = set(a), set(b)
    return bool(first and second) and len(first & second) / len(first | second) >= SAME_STORY_RATIO


def drop_repeated_stories(alerts: list[dict], state: dict, now: dt.datetime) -> list[dict]:
    """Evita varios avisos por un mismo hecho contado por distintos medios."""
    expiry = (now - dt.timedelta(hours=48)).isoformat(timespec="seconds")
    recent = [r for r in state.get("recent_alerts", []) if r["at"] >= expiry]
    unique = []
    for alert in alerts:
        words = title_words(alert["title"])
        if not any(same_story(words, r["words"]) for r in recent):
            unique.append(alert)
            recent.append({"at": now.isoformat(timespec="seconds"), "words": words})
    state["recent_alerts"] = recent
    return unique


def compile_terms(terms: list[str]) -> re.Pattern[str]:
    alternatives = [re.escape(norm(t)).replace(r"\*", "[a-z0-9]*") for t in terms]
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(alternatives) + r")(?![a-z0-9])")


def parse_date(raw: str | None, now: dt.datetime) -> dt.datetime:
    """Interpreta la fecha del feed. Si falta o es futura, usa el momento actual."""
    parsed: dt.datetime | None = None
    if raw:
        raw = raw.strip()
        try:
            parsed = email.utils.parsedate_to_datetime(raw)
        except (TypeError, ValueError, IndexError):
            try:
                parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                parsed = None
    if parsed is None:
        return now
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    parsed = parsed.astimezone(UTC)
    return min(parsed, now)


def _local(tag: object) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def parse_feed(data: bytes) -> list[dict]:
    """Lee RSS o Atom. Rechaza DOCTYPE y entidades para evitar ataques de expansión XML."""
    if re.search(rb"<!\s*(DOCTYPE|ENTITY)", data[:4096], re.I) or b"<!ENTITY" in data:
        raise ValueError("el feed declara DOCTYPE o entidades")
    root = ET.fromstring(data)
    entries: list[dict] = []
    for node in root.iter():
        if _local(node.tag) not in ("item", "entry"):
            continue
        entry: dict = {"link": "", "date": "", "summary": "", "title": "", "source": "", "source_url": "", "guid": ""}
        for child in node:
            name = _local(child.tag)
            text = (child.text or "").strip()
            if name == "title":
                entry["title"] = text
            elif name == "link":
                href = child.get("href", "")
                if text and not entry["link"]:
                    entry["link"] = text
                elif href and child.get("rel", "alternate") == "alternate":
                    entry["link"] = href
            elif name in ("pubDate", "published", "date", "issued"):
                entry["date"] = entry["date"] or text
            elif name == "updated" and not entry["date"]:
                entry["updated"] = text
            elif name in ("description", "summary", "content", "encoded"):
                entry["summary"] = entry["summary"] or text
            elif name == "source" and text:
                entry["source"] = text
                entry["source_url"] = child.get("url", "")
            elif name in ("guid", "id"):
                entry["guid"] = text
        entry["date"] = entry["date"] or entry.get("updated", "")
        if not entry["link"] and entry["guid"].startswith("http"):
            entry["link"] = entry["guid"]
        entries.append(entry)
    return entries


class Rules:
    def __init__(self, config: dict):
        rules = config["rules"]
        self.cyber = compile_terms(rules["cyber"])
        self.argentina = compile_terms(rules["argentina"])
        self.incident = compile_terms(rules["incident"])
        self.critical = compile_terms(rules["critical"])
        self.categories = [(name, compile_terms(terms)) for name, terms in config["categories"].items()]
        self.trusted = {d.lower().removeprefix("www.") for d in config.get("trusted", {}).get("outlets", [])}

    def is_trusted(self, url: str) -> bool:
        """Un agregador solo aporta notas de medios de la lista; un subdominio cuenta como su medio."""
        host = urllib.parse.urlsplit(safe_url(url)).hostname or ""
        host = host.lower().removeprefix("www.")
        return any(host == d or host.endswith("." + d) for d in self.trusted)

    def category(self, text: str) -> str:
        for name, pattern in self.categories:
            if pattern.search(text):
                return name
        return "General"


def build_item(feed: dict, entry: dict, now: dt.datetime, rules: Rules) -> dict | None:
    """Convierte una entrada cruda en un ítem de la app, o la descarta."""
    url = safe_url(clean_text(entry["link"]))
    title = clean_text(entry["title"])
    if not url or not title:
        return None

    prefix = feed.get("title_prefix")
    if prefix:
        if not title.casefold().startswith(prefix.casefold()):
            return None
        title = title[len(prefix):].strip()

    if feed.get("aggregator") and not rules.is_trusted(entry.get("source_url", "")):
        return None

    source = clean_text(entry["source"]) or feed["name"]
    suffix = f" - {source}"
    if feed.get("aggregator") and title.endswith(suffix):
        title = title[: -len(suffix)].rstrip()

    # Google Noticias solo repite el título y enlaces en la descripción.
    summary = "" if feed.get("aggregator") else truncate(clean_text(entry["summary"]), SUMMARY_MAX)
    title = truncate(title, TITLE_MAX)

    n_title = norm(title)
    haystack = f"{n_title} {norm(summary)}"
    if feed.get("require_cyber") and not rules.cyber.search(haystack):
        return None

    mentions_ar = bool(rules.argentina.search(n_title))
    critical = bool(rules.critical.search(n_title))
    alert = critical or (mentions_ar and bool(rules.incident.search(n_title)))
    published = parse_date(entry["date"], now)
    canon = canonical_url(url)

    return {
        "id": hashlib.sha256(canon.encode()).hexdigest()[:16],
        "title": title,
        "url": url,
        "source": truncate(source, 60),
        "summary": summary,
        "region": "ar" if mentions_ar else feed["region"],
        "category": rules.category(haystack),
        "alert": alert,
        "published": published.isoformat(timespec="seconds"),
        "first_seen": now.isoformat(timespec="seconds"),
        "lang": feed.get("lang", "es"),
    }


FEED_ACCEPT = "application/rss+xml, application/atom+xml, text/xml, */*"


def fetch_url(url: str, timeout: float = 25, accept: str = FEED_ACCEPT) -> bytes:
    if not url.startswith("https://"):
        raise ValueError("solo se aceptan feeds https")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": accept},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read(MAX_FEED_BYTES + 1)
    if len(data) > MAX_FEED_BYTES:
        raise ValueError("feed demasiado grande")
    return data


def send_ntfy(server: str, topic: str, payload: dict) -> None:
    body = json.dumps({"topic": topic, **payload}).encode()
    request = urllib.request.Request(
        server.rstrip("/") + "/",
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        response.read()


def alert_payload(item: dict) -> dict:
    is_ar = item["region"] == "ar"
    return {
        "title": truncate(("Argentina · " if is_ar else "") + item["title"], 180),
        "message": truncate(f"{item['source']}. {item['summary']}".rstrip(" ."), 400) or item["source"],
        "click": item["url"],
        "priority": 4 if is_ar else 3,
        "tags": ["rotating_light" if is_ar else "warning"],
    }


def digest_payload(items: list[dict], site_url: str) -> dict:
    payload = {
        "title": f"Ciber Radar: {len(items)} alertas más",
        "message": truncate(" · ".join(i["title"] for i in items[:3]), 400),
        "priority": 3,
        "tags": ["newspaper"],
    }
    if site_url:
        payload["click"] = site_url
    return payload


def process_notifications(
    queue: list[dict],
    state: dict,
    limits: dict,
    now: dt.datetime,
    topic: str,
    site_url: str,
    notify: Callable[[dict], None],
) -> None:
    """Manda lo que entra en el presupuesto y deja en espera lo que falló por red."""
    state["pending"] = []
    if not queue:
        return
    if not topic:
        log.info("sin NTFY_TOPIC: %d alertas quedan solo en la app", len(queue))
        return

    today = now.date().isoformat()
    used = state.get("notified", {}).get(today, 0)
    allowance = min(limits["notify_per_run"], limits["notify_per_day"] - used)
    if allowance <= 0:
        log.warning("presupuesto diario de avisos agotado: %d alertas quedan solo en la app", len(queue))
        return

    queue = sorted(queue, key=lambda i: (i["region"] != "ar", i["published"]))
    if len(queue) > allowance:
        individual, overflow = queue[: allowance - 1], queue[allowance - 1 :]
    else:
        individual, overflow = queue, []

    sent = 0
    try:
        for item in individual:
            notify(alert_payload(item))
            sent += 1
        if overflow:
            notify(digest_payload(overflow, site_url))
            sent += 1
    except Exception as exc:  # la red no debe frenar la publicación de la app
        log.warning("falló un aviso, se reintenta en la próxima corrida: %s", type(exc).__name__)
        state["pending"] = individual[sent:] + overflow
    state["notified"] = {today: used + sent}


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(temp, path)


def month_files(data_dir: Path) -> list[Path]:
    return sorted(data_dir.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].json"), reverse=True)


def collect_feed(feed: dict, fetch: Callable[[str], bytes]) -> tuple[list[dict], str]:
    try:
        return parse_feed(fetch(feed["url"])), ""
    except Exception as exc:  # una fuente caída no debe tirar las demás
        return [], type(exc).__name__


def run(
    config: dict,
    data_dir: Path,
    state_path: Path,
    now: dt.datetime,
    fetch: Callable[[str], bytes] = fetch_url,
    notify: Callable[[dict], None] | None = None,
    topic: str = "",
    site_url: str = "",
) -> dict:
    """Hace una corrida completa y devuelve un resumen."""
    limits = config["limits"]
    rules = Rules(config)
    feeds = config["feeds"]

    with cf.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda f: collect_feed(f, fetch), feeds))

    healthy = sum(1 for _, error in results if not error)
    if healthy < len(feeds) * MIN_HEALTHY_RATIO:
        raise RuntimeError(f"solo respondieron {healthy} de {len(feeds)} fuentes; no se toca nada")

    raw_state = read_json(state_path, None)
    first_run = raw_state is None
    state = raw_state or {"seen": {}, "pending": [], "notified": {}}
    seen: dict[str, str] = state["seen"]
    min_date = now - dt.timedelta(days=limits["max_age_days"])
    notify_after = now - dt.timedelta(hours=limits["notify_max_age_hours"])
    stamp = now.isoformat(timespec="seconds")

    new_items: list[dict] = []
    sources: list[dict] = []
    for feed, (entries, error) in zip(feeds, results):
        built = [item for e in entries if (item := build_item(feed, e, now, rules))]
        built.sort(key=lambda i: i["published"], reverse=True)
        accepted = 0
        for item in built[: limits["max_items_per_feed"]]:
            if dt.datetime.fromisoformat(item["published"]) < min_date:
                continue
            key = title_key(item["title"])
            keys = [item["id"]] + ([f"t:{key}"] if key else [])
            if any(k in seen for k in keys):
                continue
            seen.update((k, stamp) for k in keys)
            new_items.append(item)
            accepted += 1
        sources.append({"name": feed["name"], "ok": not error, "new": accepted, "error": error})

    months: dict[str, list[dict]] = {}
    for item in new_items:
        month = item["published"][:7]
        if month not in months:
            months[month] = read_json(data_dir / f"{month}.json", [])
        months[month].append(item)
    for month, items in months.items():
        items.sort(key=lambda i: i["published"], reverse=True)
        write_json(data_dir / f"{month}.json", items)

    latest: list[dict] = []
    files = month_files(data_dir)
    for path in files:
        if len(latest) >= limits["latest_items"]:
            break
        latest.extend(read_json(path, []))
    latest.sort(key=lambda i: i["published"], reverse=True)
    write_json(
        data_dir / "latest.json",
        {
            "generated": stamp,
            "sources": sources,
            "months": [p.stem for p in files],
            "items": latest[: limits["latest_items"]],
        },
    )

    alerts: list[dict] = []
    if not first_run:
        alerts = [
            i for i in new_items
            if i["alert"] and dt.datetime.fromisoformat(i["published"]) >= notify_after
        ]
    alerts = drop_repeated_stories(alerts, state, now)
    expiry = (now - dt.timedelta(hours=24)).isoformat(timespec="seconds")
    retry = [i for i in state.get("pending", []) if i["first_seen"] >= expiry]
    process_notifications(retry + alerts, state, limits, now, topic, site_url, notify or (lambda _: None))

    cutoff = (now - dt.timedelta(days=limits["seen_retention_days"])).isoformat(timespec="seconds")
    state["seen"] = {k: v for k, v in seen.items() if v >= cutoff}
    write_json(state_path, state)

    return {
        "new": len(new_items),
        "alerts": len(alerts),
        "healthy": healthy,
        "total": len(feeds),
        "first_run": first_run,
        "failed": [s["name"] for s in sources if not s["ok"]],
    }


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=root / "feeds.toml")
    parser.add_argument("--data", type=Path, default=root / "data")
    parser.add_argument("--state", type=Path, default=root / "state" / "state.json")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    config = tomllib.loads(args.config.read_text(encoding="utf-8"))
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").strip()
    site_url = safe_url(os.environ.get("SITE_URL", ""))
    try:
        report = run(
            config,
            args.data,
            args.state,
            dt.datetime.now(UTC),
            notify=lambda payload: send_ntfy(server, topic, payload),
            topic=topic,
            site_url=site_url,
        )
    except RuntimeError as exc:
        log.error("%s", exc)
        return 1
    log.info(
        "nuevas=%d alertas=%d fuentes=%d/%d caidas=%s",
        report["new"], report["alerts"], report["healthy"], report["total"], report["failed"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
