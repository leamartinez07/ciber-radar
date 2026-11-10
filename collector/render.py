#!/usr/bin/env python3
"""Genera el sitio estático completo a partir de los datos recolectados.

Cada página sale con todas sus noticias en el HTML, así carga sin esperar a JavaScript
y los buscadores la leen entera. Todo texto de un feed se escapa al escribirse.
"""
from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect import safe_url, title_words  # noqa: E402

AR = dt.timezone(dt.timedelta(hours=-3))
MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre"]
DAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
REGION_NAMES = {"ar": "Argentina", "latam": "Latinoamérica", "mundo": "Mundo"}
CRITICAL_TOPICS = {"Vulnerabilidades", "Ransomware", "Filtraciones"}
FRONT_SAME_STORY = 0.34
BULLETIN_SOURCES = {"CISA", "INCIBE-CERT"}  # boletines técnicos: útiles, pero no son titular de tapa
RIVER_ON_HOME = 42
ITEMS_PER_SECTION = 150
SITE_NAME = "Ciber Radar"
TAGLINE = "Toda la ciberseguridad, a medida que sale."
HOME_TITLE = "Ciber Radar: noticias de ciberseguridad de Argentina y el mundo"
HOME_DESCRIPTION = "Noticias de ciberseguridad de Argentina, Latinoamérica y el mundo, reunidas cada 30 minutos desde 18 fuentes: ataques, filtraciones, estafas y vulnerabilidades."
SECTIONS = [
    {"key": "ar", "slug": "argentina", "name": "Argentina",
     "description": "Ciberataques, filtraciones de datos, estafas digitales y ciberdefensa en Argentina, actualizado cada 30 minutos."},
    {"key": "latam", "slug": "latinoamerica", "name": "Latinoamérica",
     "description": "Noticias de ciberseguridad de América Latina: amenazas, incidentes y análisis regionales."},
    {"key": "mundo", "slug": "mundo", "name": "Mundo",
     "description": "Lo último en ciberseguridad internacional: ransomware, vulnerabilidades, espionaje y filtraciones."},
    {"key": "alert", "slug": "alertas", "name": "Alertas",
     "description": "Incidentes en Argentina y fallos críticos que ya se están explotando en el mundo."},
]
EMBLEM = (
    '<svg class="emblem" viewBox="0 0 100 100" aria-hidden="true" focusable="false">'
    '<circle cx="50" cy="50" r="46"/><circle cx="50" cy="50" r="28"/>'
    '<g class="sweep"><path d="M50 50 L50 4"/></g>'
    '<circle class="core" cx="50" cy="50" r="6"/><circle class="blip" cx="68" cy="66" r="5"/></svg>'
)


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def local(iso: str) -> dt.datetime:
    return dt.datetime.fromisoformat(iso).astimezone(AR)


def short_date(iso: str) -> str:
    when = local(iso)
    return f"{when.day} {MONTHS[when.month - 1][:3]}, {when:%H:%M}"


def long_day(day: dt.date) -> str:
    return f"{DAYS[day.weekday()]}, {day.day} de {MONTHS[day.month - 1]} de {day.year}"


def time_tag(iso: str) -> str:
    return f'<time datetime="{esc(iso)}" data-rel>{esc(short_date(iso))}</time>'


def kicker_text(item: dict) -> str:
    topic = item["category"] if item["category"] != "General" else REGION_NAMES[item["region"]]
    return f"Alerta · {topic}" if item["alert"] else topic


def story(item: dict, heading: str = "h3", summary: bool = True, css: str = "story") -> str:
    url = safe_url(item["url"])
    if not url:
        return ""
    lang = f' lang="{esc(item["lang"])}"' if item.get("lang", "es") != "es" else ""
    kicker = "kicker is-alert" if item["alert"] else "kicker"
    body = f'<p class="summary"{lang}>{esc(item["summary"])}</p>' if summary and item["summary"] else ""
    return (
        f'<article class="{css}" data-category="{esc(item["category"])}" data-seen="{esc(item["first_seen"])}">'
        f'<p class="{kicker}">{esc(kicker_text(item))}</p>'
        f'<{heading}{lang}><a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(item["title"])}</a></{heading}>'
        f'{body}<p class="meta">{esc(item["source"])} · {time_tag(item["published"])}</p></article>'
    )


def river(items: list[dict]) -> str:
    groups: dict[dt.date, list[str]] = {}
    for item in items:
        groups.setdefault(local(item["published"]).date(), []).append(story(item))
    return "".join(
        f'<section class="day-block"><h2 class="day" data-day="{day.isoformat()}">{esc(long_day(day))}</h2>'
        f'<div class="day-grid">{"".join(stories)}</div></section>'
        for day, stories in groups.items()
    )


def same_story(a: set[str], b: set[str]) -> bool:
    return bool(a or b) and len(a & b) / len(a | b) >= FRONT_SAME_STORY


def pick_front(items: list[dict], now: dt.datetime) -> dict:
    def within(item: dict, hours: int) -> bool:
        return dt.datetime.fromisoformat(item["published"]) >= now - dt.timedelta(hours=hours)

    is_ar_alert = lambda i: i["alert"] and i["region"] == "ar"  # noqa: E731
    pool = [i for i in items if within(i, 72)] or items
    editorial = [i for i in pool if i["source"] not in BULLETIN_SOURCES] or pool
    candidates = [
        lambda i: is_ar_alert(i) and i["summary"] and within(i, 48),
        lambda i: is_ar_alert(i) and within(i, 48),
        lambda i: i["alert"] and i["summary"] and within(i, 48),
        lambda i: is_ar_alert(i),
        lambda i: i["summary"],
        lambda i: True,
    ]
    lead = next(i for test in candidates for i in editorial if test(i))
    used = {lead["id"]}
    chosen = [set(title_words(lead["title"]))]

    def take(source: list[dict], test, count: int) -> list[dict]:
        picked: list[dict] = []
        for item in source:
            if len(picked) == count:
                break
            words = set(title_words(item["title"]))
            if item["id"] in used or not test(item) or any(same_story(words, c) for c in chosen):
                continue
            picked.append(item)
            used.add(item["id"])
            chosen.append(words)
        return picked

    subleads = take(pool, lambda i: i["summary"], 4)
    argentina = take(items, lambda i: i["region"] == "ar", 7)
    alerts = take(items, lambda i: i["alert"], 7)
    alerts += take(pool, lambda i: i["category"] in CRITICAL_TOPICS, 7 - len(alerts))
    return {"lead": lead, "subleads": subleads, "argentina": argentina, "alerts": alerts, "used": used}


def column(title: str, items: list[dict]) -> str:
    return f'<div class="column"><h2 class="column-title">{esc(title)}</h2>{"".join(story(i, summary=False) for i in items)}</div>'


def front_html(front: dict) -> str:
    subleads = "".join(story(i) for i in front["subleads"])
    subleads_html = f'<div class="subleads">{subleads}</div>' if subleads else ""
    return (
        '<section class="front" aria-label="Portada">'
        f'{column("Argentina", front["argentina"])}'
        f'<div class="lead">{story(front["lead"], heading="h2", css="lead-story")}{subleads_html}</div>'
        f'{column("Alertas y fallos críticos", front["alerts"])}</section>'
    )


def pulse(items: list[dict], now: dt.datetime) -> str:
    """Barras de notas por día en los últimos 14 días, en SVG sin JavaScript."""
    today = now.astimezone(AR).date()
    days = [today - dt.timedelta(days=13 - n) for n in range(14)]
    counts = Counter(local(i["published"]).date() for i in items)
    peak = max([counts[d] for d in days] + [1])
    bars = []
    for index, day in enumerate(days):
        height = max(2, round(counts[day] / peak * 34)) if counts[day] else 2
        css = "bar today" if day == today else "bar"
        label = f"{day.day} de {MONTHS[day.month - 1]}: {counts[day]} notas"
        bars.append(
            f'<g><title>{esc(label)}</title><rect class="hit" x="{index * 12}" y="0" width="12" height="36"/>'
            f'<rect class="{css}" x="{index * 12 + 2}" y="{36 - height}" width="8" height="{height}" rx="2"/></g>'
        )
    summary = f"Notas por día en los últimos 14 días. Máximo: {peak}. Hoy: {counts[today]}."
    return (
        f'<figure class="pulse-chart"><svg viewBox="0 0 168 36" role="img" aria-label="{esc(summary)}">{"".join(bars)}</svg>'
        f'<figcaption>Actividad, 14 días · pico {peak}</figcaption></figure>'
    )


def json_ld(data: dict) -> str:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return f'<script type="application/ld+json">{text}</script>'


class Site:
    def __init__(self, data_dir: Path, source: Path, out: Path, site_url: str, repo: str):
        self.data_dir, self.source, self.out = data_dir, source, out
        self.url, self.repo = site_url.rstrip("/"), repo
        self.latest = json.loads((data_dir / "latest.json").read_text(encoding="utf-8"))
        self.items = [i for i in self.latest["items"] if safe_url(i["url"])]
        self.months = self.latest["months"]
        self.generated = self.latest["generated"]
        self.now = dt.datetime.fromisoformat(self.generated)
        self.assets: dict[str, str] = {}
        self.pages: list[str] = []

    def write(self, relative: str, content: str | bytes) -> None:
        path = self.out / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))

    def fingerprint(self, name: str) -> str:
        data = (self.source / name).read_bytes()
        digest = hashlib.sha256(data).hexdigest()[:12]
        stem, suffix = name.rsplit(".", 1)
        public = f"/assets/{stem}.{digest}.{suffix}"
        self.write(public.lstrip("/"), data)
        self.assets[name] = public
        return public

    def status_line(self) -> str:
        day_ago = self.now - dt.timedelta(hours=24)
        alerts = sum(1 for i in self.items if i["alert"] and dt.datetime.fromisoformat(i["published"]) >= day_ago)
        sources = self.latest["sources"]
        healthy = sum(1 for s in sources if s["ok"])
        word = "alerta" if alerts == 1 else "alertas"
        return f'Actualizado {time_tag(self.generated)} · {alerts} {word} en 24 h<span class="ear-extra"> · {healthy}/{len(sources)} fuentes</span>'

    def wire(self) -> str:
        latest = next((i for i in self.items if i["alert"]), None)
        chart = pulse(self.items, self.now)
        if not latest:
            return f'<aside class="wire" aria-label="Actividad">{chart}</aside>'
        lang = f' lang="{esc(latest["lang"])}"' if latest.get("lang", "es") != "es" else ""
        return (
            '<aside class="wire" aria-label="Última alerta">'
            '<div class="wire-news"><span class="wire-label"><span class="pulse" aria-hidden="true"></span>ÚLTIMA ALERTA</span>'
            f'<a{lang} href="{esc(safe_url(latest["url"]))}" target="_blank" rel="noopener noreferrer">{esc(latest["title"])}</a>'
            f'<span class="wire-meta">{time_tag(latest["published"])}</span></div>{chart}</aside>'
        )

    def nav(self, current: str) -> str:
        entries = [("", "/", "Portada")] + [(s["key"], f'/{s["slug"]}', s["name"]) for s in SECTIONS]
        links = "".join(
            f'<a href="{href}"{" aria-current=\"page\"" if key == current else ""}>{name}</a>'
            for key, href, name in entries
        )
        return f'<nav class="sections" aria-label="Secciones"><span class="scan" aria-hidden="true"></span>{links}</nav>'

    def tools(self, items: list[dict]) -> str:
        categories = sorted({i["category"] for i in items}, key=str.casefold)
        options = "".join(f'<option value="{esc(c)}">{esc(c)}</option>' for c in categories)
        return (
            '<form class="tools" role="search" action="#" autocomplete="off">'
            '<label class="search"><span class="sr">Buscar en las noticias</span>'
            '<input id="query" type="search" placeholder="Buscar: ransomware, CVE…"></label>'
            '<label class="topic"><span class="sr">Filtrar por tema</span>'
            f'<select id="category"><option value="">Todos los temas</option>{options}</select></label>'
            '<button class="sr" type="submit">Buscar</button></form>'
        )

    def footer(self) -> str:
        sources = "".join(
            f'<li{"" if s["ok"] else " class=\"down\""}>{"OK" if s["ok"] else "CAÍDA"} · {esc(s["name"])}</li>'
            for s in self.latest["sources"]
        )
        return (
            '<footer class="colophon">'
            '<nav class="foot-links" aria-label="Más"><a href="/archivo">Archivo</a><a href="/feed.xml">RSS</a>'
            f'<a href="https://github.com/{esc(self.repo)}" rel="noopener">Código</a></nav>'
            '<details><summary>Instalar en el celular</summary><p><strong>Android:</strong> abrí el menú de Chrome y tocá «Instalar app». '
            '<strong>iPhone:</strong> en Safari tocá Compartir y «Agregar a inicio».</p></details>'
            f'<details><summary>Estado de las fuentes</summary><ul class="source-list">{sources}</ul></details>'
            '<p>Ciber Radar reúne titulares y extractos breves con enlace al medio original. Cada nota pertenece a su autor.</p>'
            '</footer>'
        )

    def page(self, relative: str, path: str, title: str, description: str, content: str, *,
             current: str = "", items: list[dict] | None = None, is_home: bool = False,
             heading: str | None = None, extra_ld: list[dict] | None = None, indexable: bool = True) -> None:
        canonical = self.url + path if path != "/" else self.url + "/"
        brand = f'<a href="/" aria-label="{SITE_NAME}, portada">Ciber {EMBLEM} Radar</a>'
        brand_tag = "h1" if is_home else "p"
        intro = f'<header class="page-head"><h1>{esc(heading)}</h1><p>{esc(description)}</p></header>' if heading else ""
        website = {"@context": "https://schema.org", "@type": "WebSite", "name": SITE_NAME, "url": self.url + "/",
                   "inLanguage": "es-AR", "description": HOME_DESCRIPTION}
        ld = "".join(json_ld(d) for d in [website, *(extra_ld or [])])
        robots = "index,follow,max-image-preview:large,max-snippet:-1" if indexable else "noindex"
        og_image = f"{self.url}/og.png"
        document = f'''<!DOCTYPE html>
<html lang="es-AR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<meta name="robots" content="{robots}">
<link rel="canonical" href="{esc(canonical)}">
<meta name="theme-color" content="#fbfaf6" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#101211" media="(prefers-color-scheme: dark)">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:locale" content="es_AR">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:image" content="{esc(og_image)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Portada de Ciber Radar, diario de ciberseguridad">
<meta name="twitter:card" content="summary_large_image">
<link rel="alternate" type="application/rss+xml" title="{SITE_NAME}" href="/feed.xml">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="icon" href="/icons/icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/icons/icon-192.png">
<link rel="preload" href="/fonts/playfair-display-latin-900-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/source-serif-4-latin-400-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{self.assets["styles.css"]}">
<script src="{self.assets["app.js"]}" defer></script>
{ld}
</head>
<body>
<a class="skip" href="#contenido">Saltar a las noticias</a>
<header class="masthead">
<div class="ears"><span id="today">{esc(long_day(self.now.astimezone(AR).date()))}</span><span class="ear-right">{self.status_line()}</span></div>
<{brand_tag} class="brand">{brand}</{brand_tag}>
<p class="motto">{TAGLINE}</p>
</header>
{self.nav(current)}
{self.wire()}
{self.tools(items if items is not None else self.items)}
<main id="contenido" data-view="{esc(current)}">
<div id="page">{intro}{content}</div>
<section id="results" aria-live="polite" hidden></section>
</main>
{self.footer()}
</body>
</html>
'''
        self.write(relative, document)
        if indexable:
            self.pages.append(path)

    def item_list(self, name: str, items: list[dict], path: str) -> dict:
        return {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": name,
            "url": self.url + path,
            "inLanguage": "es-AR",
            "mainEntity": {
                "@type": "ItemList",
                "itemListElement": [
                    {"@type": "ListItem", "position": n, "url": i["url"], "name": i["title"]}
                    for n, i in enumerate(items[:20], start=1)
                ],
            },
        }

    def more_link(self) -> str:
        month = self.months[0] if self.months else ""
        return f'<p class="more"><a href="/archivo/{esc(month)}">Ver todas las noticias del mes</a></p>' if month else ""

    def build_home(self) -> None:
        front = pick_front(self.items, self.now)
        rest = [i for i in self.items if i["id"] not in front["used"]][:RIVER_ON_HOME]
        content = front_html(front) + f'<div class="river">{river(rest)}</div>' + self.more_link()
        self.page("index.html", "/", HOME_TITLE, HOME_DESCRIPTION, content, is_home=True,
                  extra_ld=[self.item_list(HOME_TITLE, self.items, "/")])

    def build_sections(self) -> None:
        for section in SECTIONS:
            key = section["key"]
            items = [i for i in self.items if (i["alert"] if key == "alert" else i["region"] == key)]
            shown = items[:ITEMS_PER_SECTION]
            empty = '<p class="notice">Todavía no hay noticias en esta sección.</p>'
            content = (f'<div class="river">{river(shown)}</div>' if shown else empty) + self.more_link()
            path = f'/{section["slug"]}'
            title = f'{section["name"]}: noticias de ciberseguridad | {SITE_NAME}'
            self.page(f'{section["slug"]}.html', path, title, section["description"], content, current=key,
                      items=shown, heading=section["name"], extra_ld=[self.item_list(title, shown, path)])

    def build_archive(self) -> None:
        rows = []
        for month in self.months:
            items = json.loads((self.data_dir / f"{month}.json").read_text(encoding="utf-8"))
            items = [i for i in items if safe_url(i["url"])]
            year, number = month.split("-")
            name = f"{MONTHS[int(number) - 1].capitalize()} de {year}"
            rows.append(f'<li><a href="/archivo/{esc(month)}">{esc(name)}</a><span>{len(items)} notas</span></li>')
            path = f"/archivo/{month}"
            description = f"Todas las noticias de ciberseguridad de {name.lower()} reunidas por Ciber Radar."
            self.page(f"archivo/{month}.html", path, f"{name}: archivo de ciberseguridad | {SITE_NAME}", description,
                      f'<div class="river">{river(items)}</div>', items=items, heading=name)
        description = "Archivo mensual de las noticias de ciberseguridad reunidas por Ciber Radar."
        self.page("archivo.html", "/archivo", f"Archivo | {SITE_NAME}", description,
                  f'<ul class="archive">{"".join(rows)}</ul>', items=[], heading="Archivo")

    def build_404(self) -> None:
        self.page("404.html", "/404", f"Página no encontrada | {SITE_NAME}", "Esta página no existe.",
                  '<p class="notice">Esta edición no existe. <a href="/">Volver a la portada</a>.</p>',
                  items=[], heading="Página no encontrada", indexable=False)

    def build_feed(self) -> None:
        entries = []
        for item in self.items[:50]:
            published = email.utils.format_datetime(dt.datetime.fromisoformat(item["published"]))
            entries.append(
                f'<item><title>{xml_escape(item["title"])}</title><link>{xml_escape(item["url"])}</link>'
                f'<guid isPermaLink="false">{xml_escape(item["id"])}</guid><pubDate>{published}</pubDate>'
                f'<description>{xml_escape(item["source"] + ". " + item["summary"])}</description></item>'
            )
        built = email.utils.format_datetime(self.now)
        self.write(
            "feed.xml",
            '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
            f'<title>{SITE_NAME}</title><link>{xml_escape(self.url)}/</link><description>{xml_escape(HOME_DESCRIPTION)}</description>'
            f'<language>es-AR</language><lastBuildDate>{built}</lastBuildDate>'
            f'<atom:link href="{xml_escape(self.url)}/feed.xml" rel="self" type="application/rss+xml"/>{"".join(entries)}</channel></rss>\n',
        )

    def build_discovery(self) -> None:
        stamp = self.now.date().isoformat()
        urls = "".join(
            f"<url><loc>{xml_escape(self.url + (p if p != '/' else '/'))}</loc><lastmod>{stamp}</lastmod></url>"
            for p in self.pages
        )
        self.write(
            "sitemap.xml",
            f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n',
        )
        self.write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {self.url}/sitemap.xml\n")
        expires = (self.now + dt.timedelta(days=330)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.write(
            ".well-known/security.txt",
            f"Contact: https://github.com/{self.repo}/security/advisories/new\nExpires: {expires}\n"
            f"Preferred-Languages: es, en\nCanonical: {self.url}/.well-known/security.txt\n",
        )

    def build_static(self) -> None:
        for name in ("fonts", "icons"):
            shutil.copytree(self.source / name, self.out / name)
        shutil.copy2(self.source / "og.png", self.out / "og.png")
        shutil.copy2(self.source / "manifest.webmanifest", self.out / "manifest.webmanifest")
        self.write("data/latest.json", json.dumps({"items": self.items}, ensure_ascii=False, separators=(",", ":")))
        precache = ["/", self.assets["styles.css"], self.assets["app.js"], "/data/latest.json", "/icons/icon-192.png"]
        precache += sorted(f"/fonts/{p.name}" for p in (self.source / "fonts").glob("*.woff2"))
        version = hashlib.sha256("".join(precache).encode()).hexdigest()[:12]
        worker = (self.source / "sw.js").read_text(encoding="utf-8")
        self.write("sw.js", worker.replace("__PRECACHE__", json.dumps(precache)).replace("__VERSION__", version))

    def build(self) -> None:
        if self.out.exists():
            shutil.rmtree(self.out)
        self.out.mkdir(parents=True)
        self.fingerprint("styles.css")
        self.fingerprint("app.js")
        self.build_home()
        self.build_sections()
        self.build_archive()
        self.build_404()
        self.build_feed()
        self.build_discovery()
        self.build_static()


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=root / "data")
    parser.add_argument("--source", type=Path, default=root / "site")
    parser.add_argument("--out", type=Path, default=root / "public")
    args = parser.parse_args()
    site_url = safe_url(os.environ.get("SITE_URL", "")) or "https://ciber-radar.vercel.app"
    repo = os.environ.get("GITHUB_REPOSITORY", "leamartinez07/ciber-radar")
    Site(args.data, args.source, args.out, site_url, repo).build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
