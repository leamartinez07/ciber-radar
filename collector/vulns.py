#!/usr/bin/env python3
"""Vulnerabilidades explotadas y críticas, desde fuentes oficiales y gratuitas, sin clave.

- CISA KEV (CC0 1.0): fallos con explotación confirmada en el mundo real.
- FIRST EPSS: probabilidad de que un CVE se explote en los próximos 30 días.
- NVD API 2.0 (NIST): CVE críticos (CVSS 9 o más) publicados en las últimas 72 horas.

Todo lo que llega se valida y se trata como dato no confiable. Si una fuente falla,
se conserva lo último bueno de esa fuente, así una caída no vacía la página.
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
import urllib.parse
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect import UTC, clean_text, fetch_url, read_json, send_ntfy, truncate, write_json  # noqa: E402

log = logging.getLogger("ciber-radar")

KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
EPSS_URL = "https://api.first.org/data/v1/epss"
NVD_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
CVE = re.compile(r"^CVE-\d{4}-\d{4,7}$")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
KEV_DAYS = 30
KEV_MAX = 60
NVD_HOURS = 72
NVD_MAX = 60
EPSS_BATCH = 60
NOTIFY_MAX = 4
RETRY_SECONDS = 4


def nvd_link(cve: str) -> str:
    return f"https://nvd.nist.gov/vuln/detail/{cve}"


def text(value: object, limit: int) -> str:
    return truncate(clean_text(value if isinstance(value, str) else ""), limit)


def parse_kev(data: dict, now: dt.datetime) -> tuple[list[dict], int]:
    since = (now - dt.timedelta(days=KEV_DAYS)).date().isoformat()
    entries = []
    for raw in data.get("vulnerabilities", []):
        cve, added = raw.get("cveID", ""), raw.get("dateAdded", "")
        if not isinstance(cve, str) or not CVE.match(cve) or not isinstance(added, str) or not DAY.match(added):
            continue
        if added < since:
            continue
        due = raw.get("dueDate", "")
        entries.append({
            "cve": cve,
            "vendor": text(raw.get("vendorProject"), 60),
            "product": text(raw.get("product"), 80),
            "name": text(raw.get("vulnerabilityName"), 140),
            "description": text(raw.get("shortDescription"), 320),
            "added": added,
            "due": due if isinstance(due, str) and DAY.match(due) else "",
            "ransomware": raw.get("knownRansomwareCampaignUse") == "Known",
            "url": nvd_link(cve),
        })
    entries.sort(key=lambda e: (e["added"], e["cve"]), reverse=True)
    return entries[:KEV_MAX], len(data.get("vulnerabilities", []))


def cvss(metrics: dict) -> tuple[float, str]:
    """El puntaje más alto entre CVSS 4.0 y 3.x, con su versión."""
    best, version = 0.0, ""
    for key, label in (("cvssMetricV40", "4.0"), ("cvssMetricV31", "3.1"), ("cvssMetricV30", "3.0")):
        for metric in metrics.get(key, []) or []:
            score = (metric.get("cvssData") or {}).get("baseScore")
            if isinstance(score, (int, float)) and 0 <= score <= 10 and score > best:
                best, version = float(score), label
    return best, version


def parse_nvd(data: dict) -> list[dict]:
    entries = []
    for wrapper in data.get("vulnerabilities", []):
        cve = wrapper.get("cve") or {}
        cid = cve.get("id", "")
        if not isinstance(cid, str) or not CVE.match(cid) or cve.get("vulnStatus") == "Rejected":
            continue
        score, version = cvss(cve.get("metrics") or {})
        if score < 9.0:
            continue
        description = next((d.get("value", "") for d in cve.get("descriptions", []) if d.get("lang") == "en"), "")
        published = cve.get("published", "")
        try:
            published = dt.datetime.fromisoformat(published).replace(tzinfo=UTC).isoformat(timespec="seconds")
        except (TypeError, ValueError):
            continue
        entries.append({"cve": cid, "score": score, "cvss": version, "description": text(description, 320),
                        "published": published, "url": nvd_link(cid)})
    unique = {e["cve"]: e for e in entries}
    return sorted(unique.values(), key=lambda e: (e["score"], e["published"]), reverse=True)[:NVD_MAX]


def nvd_query(now: dt.datetime, severity_param: str) -> str:
    start = (now - dt.timedelta(hours=NVD_HOURS)).strftime("%Y-%m-%dT%H:%M:%S.000")
    end = now.strftime("%Y-%m-%dT%H:%M:%S.000")
    query = urllib.parse.urlencode({severity_param: "CRITICAL", "pubStartDate": start, "pubEndDate": end,
                                    "resultsPerPage": 200, "noRejected": ""})
    return f"{NVD_URL}?{query}".replace("noRejected=", "noRejected")


def parse_epss(data: dict) -> dict[str, dict]:
    scores = {}
    for row in data.get("data", []):
        try:
            cve, epss, pct = row["cve"], float(row["epss"]), float(row["percentile"])
        except (KeyError, TypeError, ValueError):
            continue
        if isinstance(cve, str) and CVE.match(cve) and 0 <= epss <= 1 and 0 <= pct <= 1:
            scores[cve] = {"epss": round(epss, 4), "percentile": round(pct, 4)}
    return scores


def get_json(fetch: Callable[[str], bytes], url: str, retries: int = 2) -> dict:
    """Las APIs públicas a veces rechazan un pedido suelto: se reintenta con espera creciente."""
    for attempt in range(retries + 1):
        try:
            data = json.loads(fetch(url))
            break
        except (OSError, ValueError):
            if attempt == retries:
                raise
            time.sleep(RETRY_SECONDS * (attempt + 1))
    if not isinstance(data, dict):
        raise ValueError("respuesta inesperada")
    return data


def fetch_json(url: str) -> bytes:
    # EPSS rechaza los pedidos que aceptan XML primero, así que acá se pide JSON.
    return fetch_url(url, accept="application/json")


def build(now: dt.datetime, previous: dict, fetch: Callable[[str], bytes] = fetch_json) -> dict:
    sources = []

    def attempt(name: str, job: Callable[[], object], fallback: object) -> object:
        try:
            value = job()
            sources.append({"name": name, "ok": True, "error": ""})
            return value
        except Exception as exc:  # una fuente caída conserva sus datos anteriores
            log.warning("%s no respondió: %s", name, type(exc).__name__)
            sources.append({"name": name, "ok": False, "error": type(exc).__name__})
            return fallback

    kev, kev_total = attempt("CISA KEV", lambda: parse_kev(get_json(fetch, KEV_URL), now),
                             (previous.get("kev", []), previous.get("kev_total", 0)))

    def critical() -> list[dict]:
        found: list[dict] = []
        for param in ("cvssV3Severity", "cvssV4Severity"):
            found += parse_nvd(get_json(fetch, nvd_query(now, param)))
        unique = {e["cve"]: e for e in found}
        return sorted(unique.values(), key=lambda e: (e["score"], e["published"]), reverse=True)[:NVD_MAX]

    nvd = attempt("NVD (NIST)", critical, previous.get("critical", []))

    old_scores = {e["cve"]: {"epss": e.get("epss"), "percentile": e.get("percentile")}
                  for e in previous.get("kev", []) + previous.get("critical", []) if e.get("epss") is not None}

    def scores() -> dict[str, dict]:
        ids = sorted({e["cve"] for e in kev + nvd})
        result: dict[str, dict] = {}
        for start in range(0, len(ids), EPSS_BATCH):
            batch = ",".join(ids[start:start + EPSS_BATCH])
            # Los CVE ya están validados: van tal cual, separados por coma.
            result.update(parse_epss(get_json(fetch, f"{EPSS_URL}?cve={batch}")))
        return result

    epss = attempt("FIRST EPSS", scores, old_scores)
    for entry in kev + nvd:
        entry.update(epss.get(entry["cve"], {"epss": None, "percentile": None}))

    return {"generated": now.isoformat(timespec="seconds"), "kev": kev, "kev_total": kev_total,
            "critical": nvd, "sources": sources}


def kev_alert(entry: dict) -> dict:
    ransomware = " Usada por ransomware." if entry["ransomware"] else ""
    return {
        "title": truncate(f"Explotada: {entry['cve']} · {entry['vendor']} {entry['product']}", 180),
        "message": truncate(f"{entry['name']}. CISA confirmó explotación activa.{ransomware}", 400),
        "click": entry["url"],
        "priority": 4,
        "tags": ["rotating_light"],
    }


def new_kev(previous: dict, current: dict) -> list[dict]:
    """Solo avisa altas nuevas de KEV, y nunca en la primera corrida."""
    if not previous.get("kev"):
        return []
    known = {e["cve"] for e in previous["kev"]}
    return [e for e in current["kev"] if e["cve"] not in known]


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=root / "data")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    path = args.data / "vulns.json"
    previous = read_json(path, {})
    current = build(dt.datetime.now(UTC), previous)
    if not any(s["ok"] for s in current["sources"]):
        log.error("ninguna fuente de vulnerabilidades respondió; no se toca nada")
        return 1
    write_json(path, current)

    fresh = new_kev(previous, current)
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if fresh and topic:
        server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").strip()
        for entry in fresh[:NOTIFY_MAX]:
            try:
                send_ntfy(server, topic, kev_alert(entry))
            except Exception as exc:  # el aviso no debe frenar la publicación
                log.warning("falló un aviso de KEV: %s", type(exc).__name__)
                break
    log.info("kev=%d criticas=%d nuevas_kev=%d fuentes=%s", len(current["kev"]), len(current["critical"]), len(fresh),
             ",".join(f"{s['name']}:{'ok' if s['ok'] else s['error']}" for s in current["sources"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
