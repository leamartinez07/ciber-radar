#!/usr/bin/env python3
"""Genera el sitio estático completo, en español y en inglés, a partir de los datos recolectados.

Cada página sale con todas sus noticias en el HTML, así carga sin esperar a JavaScript
y los buscadores la leen entera. Todo texto de un feed o de una API se escapa al escribirse.
El español vive en la raíz y el inglés bajo /en, con enlaces hreflang entre ambos.
"""
from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import hashlib
import html
import json
import math
import os
import re
import shutil
import sys
import tomllib
from collections import Counter
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect import norm, safe_url, title_words  # noqa: E402

AR = dt.timezone(dt.timedelta(hours=-3))
CRITICAL_TOPICS = {"Vulnerabilidades", "Ransomware", "Filtraciones"}
FRONT_SAME_STORY = 0.34
BULLETIN_SOURCES = {"CISA", "INCIBE-CERT", "NCSC (Reino Unido)"}  # boletines: útiles, pero no son titular de tapa
RIVER_ON_HOME = 42
ITEMS_PER_SECTION = 150
KEV_ON_HOME = 5
EPSS_HIGH = 0.1
SITE_NAME = "Ciber Radar"
OWNER = "Leandro Martinez"
OWNER_EMAIL = "leaamartinez7@gmail.com"
OWNER_URL = "https://leandromartinez.vercel.app"

# Textos de la interfaz. Las claves de categoría y región quedan en español en los datos.
LANGS = {
    "es": {
        "html": "es-AR", "og": "es_AR", "prefix": "",
        "months": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                   "septiembre", "octubre", "noviembre", "diciembre"],
        "days": ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"],
        "regions": {"ar": "Argentina", "latam": "Latinoamérica", "mundo": "Mundo"},
        "categories": {},
        "tagline": "Toda la ciberseguridad, a medida que sale.",
        "masthead_sub": "Noticias de ciberseguridad · Argentina, Latinoamérica y el mundo",
        "today_label": "Hoy:", "view_all": "Ver todo", "latest_title": "Últimas noticias",
        "data_title": "El radar en datos",
        "data_sub": "Qué países, qué temas y qué fuentes aparecen en las {n} notas más recientes.",
        "map_title": "Dónde pasa", "map_alt": "Mapa del mundo con un círculo por país mencionado. Los más nombrados: {top}.",
        "map_caption": "Países nombrados en titulares y resúmenes. El círculo crece con la cantidad de notas.",
        "rank_title": "Países más nombrados", "topics_title": "De qué se habla", "days_title": "Notas por día",
        "trust_title": "De dónde viene la información",
        "trust_kinds": {"oficial": "Organismos oficiales", "investigacion": "Investigación propia",
                        "especializado": "Medios especializados", "prensa": "Prensa general verificada"},
        "trust_note": "{ok} de {total} fuentes respondieron en la última actualización. De la prensa general solo entran medios de una lista revisada a mano.",
        "note_count": ("nota", "notas"),
        "home_title": "Ciber Radar: noticias de ciberseguridad de Argentina y el mundo",
        "home_description": "Noticias de ciberseguridad de Argentina, Latinoamérica y el mundo, y vulnerabilidades explotadas en tiempo real. Fuentes verificadas, cada 30 minutos.",
        "home": "Portada", "front": "Portada", "alert": "Alerta", "skip": "Saltar a las noticias",
        "updated": "Actualizado", "alerts_24h": ("alerta", "alertas"), "in_24h": "en 24 h", "sources": "fuentes",
        "col_ar": "Argentina", "col_alerts": "Alertas y fallos críticos",
        "latest_alert": "Última alerta", "activity": "Actividad", "last_alert_label": "Última alerta",
        "pulse_day": "{day}: {n} notas", "pulse_summary": "Notas por día en los últimos 14 días. Máximo: {peak}. Hoy: {today}.",
        "pulse_caption": "Actividad, 14 días · pico {peak}",
        "search_label": "Buscar en las noticias", "search_ph": "Buscar ransomware, CVE, bancos…",
        "topic_label": "Filtrar por tema", "all_topics": "Todos los temas", "search_btn": "Buscar",
        "sections_label": "Secciones", "more_month": "Ver todas las noticias del mes",
        "empty": "Todavía no hay noticias en esta sección.",
        "archive": "Archivo", "archive_desc": "Archivo mensual de las noticias de ciberseguridad reunidas por Ciber Radar.",
        "archive_month_title": "{name}: archivo de ciberseguridad", "archive_month_desc": "Todas las noticias de ciberseguridad de {name} reunidas por Ciber Radar.",
        "month_name": "{month} de {year}", "notes": "notas",
        "section_title": "{name}: noticias de ciberseguridad",
        "not_found": "Página no encontrada", "not_found_text": "Esta página no existe.", "back_home": "Volver a la portada",
        "lang_switch": "English", "lang_switch_label": "Read in English",
        "diary": "Diario", "contact": "Contacto", "portfolio": "Portfolio",
        "about": "Ciber Radar es un proyecto de {owner}: reúne cada 30 minutos las noticias de ciberseguridad de fuentes verificadas y las vulnerabilidades que ya se están explotando, y avisa al celular cuando algo es grave.",
        "install": "Instalar en el celular",
        "install_text": "<strong>Android:</strong> abrí el menú de Chrome y tocá «Instalar app». <strong>iPhone:</strong> en Safari tocá Compartir y «Agregar a inicio».",
        "status": "Estado de las fuentes", "ok": "OK", "down": "Caída",
        "rights": "Todos los derechos reservados.", "role": "Diseño y desarrollo web.",
        "credits": "Los titulares y extractos pertenecen a cada medio, con enlace a la nota original.",
        "nvd_notice": "Este sitio usa datos de la API de la NVD, pero la NVD no lo respalda ni lo certifica.",
        "theme": "Tema: automático",
        "vulns": "Vulnerabilidades",
        "vulns_desc": "Fallos que ya se están explotando (catálogo KEV de CISA) y CVE críticos recién publicados (NVD), con la probabilidad de explotación de EPSS. Se actualiza cada 30 minutos.",
        "vulns_title": "Vulnerabilidades explotadas y críticas, en tiempo real",
        "kev_heading": "Explotadas ahora", "kev_sub": "Altas en el catálogo KEV de CISA en los últimos 30 días: hay evidencia de ataques reales.",
        "nvd_heading": "Críticas nuevas", "nvd_sub": "CVE con puntaje CVSS de 9 o más publicados en las últimas 72 horas en la NVD.",
        "home_kev": "Radar de vulnerabilidades", "home_kev_more": "Ver todas las vulnerabilidades",
        "th_cve": "CVE", "th_product": "Producto", "th_flaw": "Fallo", "th_added": "Agregada", "th_due": "Plazo",
        "th_epss": "EPSS", "th_cvss": "CVSS", "th_published": "Publicada", "th_desc": "Descripción",
        "ransomware": "Ransomware", "epss_hint": "Probabilidad de explotación en 30 días",
        "vuln_stats": "{kev} altas en KEV en 30 días · {nvd} CVE críticos en 72 h · {total} fallos en el catálogo KEV",
        "vuln_sources": "Fuentes: CISA KEV (CC0 1.0), FIRST EPSS y NVD de NIST.",
        "no_vulns": "No hay datos de vulnerabilidades por ahora.",
        "vuln_filter": "Filtrar vulnerabilidades", "vuln_filter_ph": "Filtrar por CVE, fabricante o producto…",
        "vuln_none": "Ninguna vulnerabilidad coincide con el filtro.",
        "sec": {
            "ar": ("argentina", "Argentina", "Ciberataques, filtraciones de datos, estafas digitales y ciberdefensa en Argentina, actualizado cada 30 minutos."),
            "latam": ("latinoamerica", "Latinoamérica", "Noticias de ciberseguridad de América Latina: amenazas, incidentes y análisis regionales."),
            "mundo": ("mundo", "Mundo", "Lo último en ciberseguridad internacional: ransomware, vulnerabilidades, espionaje y filtraciones."),
            "alert": ("alertas", "Alertas", "Incidentes en Argentina y fallos críticos que ya se están explotando en el mundo."),
            "vulns": ("vulnerabilidades", "Vulnerabilidades", ""),
            "archive": ("archivo", "Archivo", ""),
            "notfound": ("404", "Página no encontrada", ""),
        },
    },
    "en": {
        "html": "en", "og": "en_US", "prefix": "/en",
        "months": ["January", "February", "March", "April", "May", "June", "July", "August",
                   "September", "October", "November", "December"],
        "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "regions": {"ar": "Argentina", "latam": "Latin America", "mundo": "World"},
        "categories": {"Ransomware": "Ransomware", "Filtraciones": "Data breaches", "Estafas": "Scams",
                       "Deepfakes e IA": "Deepfakes & AI", "Vulnerabilidades": "Vulnerabilities",
                       "Malware": "Malware", "Estado y defensa": "Government & defense", "General": "General"},
        "tagline": "All of cybersecurity, as it breaks.",
        "masthead_sub": "Cybersecurity news · Argentina, Latin America and the world",
        "today_label": "Today:", "view_all": "View all", "latest_title": "Latest news",
        "data_title": "The radar in numbers",
        "data_sub": "Which countries, topics and sources appear in the {n} most recent stories.",
        "map_title": "Where it happens", "map_alt": "World map with one circle per country mentioned. Most named: {top}.",
        "map_caption": "Countries named in headlines and summaries. The circle grows with the number of stories.",
        "rank_title": "Most named countries", "topics_title": "What is being covered", "days_title": "Stories per day",
        "trust_title": "Where the information comes from",
        "trust_kinds": {"oficial": "Official bodies", "investigacion": "Original research",
                        "especializado": "Specialist outlets", "prensa": "Verified general press"},
        "trust_note": "{ok} of {total} sources answered in the last update. From the general press, only outlets on a hand-reviewed list are included.",
        "note_count": ("story", "stories"),
        "home_title": "Ciber Radar: cybersecurity news from Argentina, Latin America and the world",
        "home_description": "Cybersecurity news from Argentina, Latin America and the world, plus exploited vulnerabilities in real time. Verified sources, every 30 minutes.",
        "home": "Home", "front": "Front page", "alert": "Alert", "skip": "Skip to the news",
        "updated": "Updated", "alerts_24h": ("alert", "alerts"), "in_24h": "in 24 h", "sources": "sources",
        "col_ar": "Argentina", "col_alerts": "Alerts and critical flaws",
        "latest_alert": "Latest alert", "activity": "Activity", "last_alert_label": "Latest alert",
        "pulse_day": "{day}: {n} stories", "pulse_summary": "Stories per day over the last 14 days. Peak: {peak}. Today: {today}.",
        "pulse_caption": "Activity, 14 days · peak {peak}",
        "search_label": "Search the news", "search_ph": "Search ransomware, CVE, banks…",
        "topic_label": "Filter by topic", "all_topics": "All topics", "search_btn": "Search",
        "sections_label": "Sections", "more_month": "See every story this month",
        "empty": "No stories in this section yet.",
        "archive": "Archive", "archive_desc": "Monthly archive of the cybersecurity news gathered by Ciber Radar.",
        "archive_month_title": "{name}: cybersecurity archive", "archive_month_desc": "Every cybersecurity story from {name} gathered by Ciber Radar.",
        "month_name": "{month} {year}", "notes": "stories",
        "section_title": "{name}: cybersecurity news",
        "not_found": "Page not found", "not_found_text": "This page does not exist.", "back_home": "Back to the front page",
        "lang_switch": "Español", "lang_switch_label": "Leer en español",
        "diary": "Explore", "contact": "Contact", "portfolio": "Portfolio",
        "about": "Ciber Radar is a project by {owner}: every 30 minutes it gathers cybersecurity news from verified sources and the vulnerabilities already being exploited, and sends a phone alert when something is serious.",
        "install": "Install on your phone",
        "install_text": "<strong>Android:</strong> open the Chrome menu and tap “Install app”. <strong>iPhone:</strong> in Safari tap Share, then “Add to Home Screen”.",
        "status": "Source status", "ok": "OK", "down": "Down",
        "rights": "All rights reserved.", "role": "Web design and development.",
        "credits": "Headlines and excerpts belong to each outlet, linked to the original story.",
        "nvd_notice": "This product uses data from the NVD API but is not endorsed or certified by the NVD.",
        "theme": "Theme: automatic",
        "vulns": "Vulnerabilities",
        "vulns_desc": "Flaws already being exploited (CISA's KEV catalog) and newly published critical CVEs (NVD), with EPSS exploitation probability. Updated every 30 minutes.",
        "vulns_title": "Exploited and critical vulnerabilities, in real time",
        "kev_heading": "Exploited now", "kev_sub": "Added to CISA's KEV catalog in the last 30 days: there is evidence of real-world attacks.",
        "nvd_heading": "New critical CVEs", "nvd_sub": "CVEs scored CVSS 9 or higher, published to the NVD in the last 72 hours.",
        "home_kev": "Vulnerability radar", "home_kev_more": "See all vulnerabilities",
        "th_cve": "CVE", "th_product": "Product", "th_flaw": "Flaw", "th_added": "Added", "th_due": "Deadline",
        "th_epss": "EPSS", "th_cvss": "CVSS", "th_published": "Published", "th_desc": "Description",
        "ransomware": "Ransomware", "epss_hint": "Probability of exploitation in 30 days",
        "vuln_stats": "{kev} KEV additions in 30 days · {nvd} critical CVEs in 72 h · {total} flaws in the KEV catalog",
        "vuln_sources": "Sources: CISA KEV (CC0 1.0), FIRST EPSS and NIST's NVD.",
        "no_vulns": "No vulnerability data right now.",
        "vuln_filter": "Filter vulnerabilities", "vuln_filter_ph": "Filter by CVE, vendor or product…",
        "vuln_none": "No vulnerability matches the filter.",
        "sec": {
            "ar": ("argentina", "Argentina", "Cyberattacks, data breaches, online scams and cyber defense in Argentina, updated every 30 minutes."),
            "latam": ("latin-america", "Latin America", "Cybersecurity news from Latin America: threats, incidents and regional analysis."),
            "mundo": ("world", "World", "The latest in international cybersecurity: ransomware, vulnerabilities, espionage and data breaches."),
            "alert": ("alerts", "Alerts", "Incidents in Argentina and critical flaws already being exploited around the world."),
            "vulns": ("vulnerabilities", "Vulnerabilities", ""),
            "archive": ("archive", "Archive", ""),
            "notfound": ("404", "Page not found", ""),
        },
    },
}
NEWS_SECTIONS = ["ar", "latam", "mundo", "alert"]

# Mapa: contorno de Natural Earth 1:110m (dominio público), ya proyectado a una caja de 1000 × 460
# que va de 84° N a 58° S. Lo genera tools/make_map.py.
MAP_W, MAP_H, MAP_TOP, MAP_BOTTOM = 1000, 460, 84, -58
WORLD_LAND = (Path(__file__).resolve().parent / "world_land.txt").read_text(encoding="utf-8").strip()
# País: nombre en español, en inglés, longitud, latitud y los términos que lo delatan en un texto sin acentos.
COUNTRIES = {
    "ar": ("Argentina", "Argentina", -64, -35, ["argentina", "argentinas", "argentino", "argentinos", "buenos aires"]),
    "br": ("Brasil", "Brazil", -52, -10, ["brasil", "brazil", "brasileno", "brasilena", "brazilian"]),
    "cl": ("Chile", "Chile", -71, -33, ["chile", "chileno", "chilena", "chilean"]),
    "uy": ("Uruguay", "Uruguay", -56, -33, ["uruguay", "uruguayo", "uruguaya"]),
    "py": ("Paraguay", "Paraguay", -58, -23, ["paraguay", "paraguayo", "paraguaya"]),
    "bo": ("Bolivia", "Bolivia", -65, -17, ["bolivia", "boliviano", "boliviana"]),
    "pe": ("Perú", "Peru", -75, -10, ["peru", "peruano", "peruana", "peruvian"]),
    "ec": ("Ecuador", "Ecuador", -78, -1.5, ["ecuador", "ecuatoriano", "ecuatoriana"]),
    "co": ("Colombia", "Colombia", -73, 4, ["colombia", "colombiano", "colombiana", "colombian"]),
    "ve": ("Venezuela", "Venezuela", -66, 7, ["venezuela", "venezolano", "venezolana"]),
    "mx": ("México", "Mexico", -102, 23, ["mexico", "mexicano", "mexicana", "mexican"]),
    "cr": ("Costa Rica", "Costa Rica", -84, 10, ["costa rica"]),
    "pa": ("Panamá", "Panama", -80, 8.5, ["panama"]),
    "do": ("República Dominicana", "Dominican Republic", -70, 19, ["republica dominicana", "dominican republic"]),
    "gt": ("Guatemala", "Guatemala", -90, 15.5, ["guatemala"]),
    "cu": ("Cuba", "Cuba", -79, 21.5, ["cuba"]),
    "us": ("Estados Unidos", "United States", -98, 39, ["estados unidos", "ee uu", "eeuu", "united states", "u s", "usa", "estadounidense", "pentagono", "pentagon"]),
    "ca": ("Canadá", "Canada", -106, 56, ["canada", "canadian", "canadiense"]),
    "gb": ("Reino Unido", "United Kingdom", -2, 54, ["reino unido", "united kingdom", "uk", "britain", "british", "britanico", "britanica"]),
    "es": ("España", "Spain", -3.7, 40, ["espana", "espanol", "espanola", "spain", "spanish"]),
    "fr": ("Francia", "France", 2.5, 46.5, ["francia", "frances", "francesa", "france", "french"]),
    "de": ("Alemania", "Germany", 10, 51, ["alemania", "aleman", "alemana", "germany", "german"]),
    "it": ("Italia", "Italy", 12.5, 42.5, ["italia", "italiano", "italiana", "italy", "italian"]),
    "nl": ("Países Bajos", "Netherlands", 5.5, 52.3, ["paises bajos", "holanda", "netherlands", "dutch"]),
    "pl": ("Polonia", "Poland", 19.5, 52, ["polonia", "poland", "polish"]),
    "ua": ("Ucrania", "Ukraine", 31, 49, ["ucrania", "ucraniano", "ukraine", "ukrainian"]),
    "ru": ("Rusia", "Russia", 60, 58, ["rusia", "ruso", "rusa", "rusos", "russia", "russian", "kremlin"]),
    "tr": ("Turquía", "Turkey", 35, 39, ["turquia", "turkey", "turkiye", "turkish"]),
    "il": ("Israel", "Israel", 35, 31.3, ["israel", "israeli"]),
    "ir": ("Irán", "Iran", 53, 32.5, ["iran", "irani", "iranian"]),
    "in": ("India", "India", 79, 22, ["india", "indian"]),
    "cn": ("China", "China", 104, 35, ["china", "chino", "chinos", "chinese", "beijing", "pekin"]),
    "kp": ("Corea del Norte", "North Korea", 127, 40, ["corea del norte", "north korea", "north korean", "norcoreano", "norcoreanos", "lazarus"]),
    "kr": ("Corea del Sur", "South Korea", 127.8, 36, ["corea del sur", "south korea", "south korean", "surcoreano"]),
    "jp": ("Japón", "Japan", 138, 36.5, ["japon", "japones", "japan", "japanese"]),
    "tw": ("Taiwán", "Taiwan", 121, 23.7, ["taiwan"]),
    "au": ("Australia", "Australia", 134, -25, ["australia", "australian", "australiano"]),
    "za": ("Sudáfrica", "South Africa", 24, -29, ["sudafrica", "south africa"]),
    "ng": ("Nigeria", "Nigeria", 8, 9.5, ["nigeria", "nigerian", "nigeriano"]),
}
COUNTRY_PATTERNS = {
    code: re.compile(r"(?<![a-z0-9])(?:" + "|".join(re.escape(t) for t in terms) + r")(?![a-z0-9])")
    for code, (_, _, _, _, terms) in COUNTRIES.items()
}
TRUST_ORDER = ["oficial", "investigacion", "especializado", "prensa"]


def source_kinds() -> dict[str, str]:
    """Tipo de cada fuente directa, según feeds.toml. Lo que llega por un agregador es prensa general."""
    config = tomllib.loads((Path(__file__).resolve().parent.parent / "feeds.toml").read_text(encoding="utf-8"))
    return {f["name"]: f.get("kind", "especializado") for f in config["feeds"] if not f.get("aggregator")}


# Marca LM de Leandro Martinez, la misma del portfolio.
BRAND_MARK = (
    '<svg class="lm" viewBox="0 0 64 64" aria-hidden="true" focusable="false">'
    '<rect class="lm-bg" x="1.5" y="1.5" width="61" height="61" rx="2"/>'
    '<g transform="translate(-2.2 3) scale(.29)"><path class="lm-m" d="M40 30H70L118 92L166 30H196V146L172 170H168V78L126 130H110L68 78V142H40Z"/>'
    '<path class="lm-bar" d="M40 142H128V170H40Z"/></g></svg>'
)
THEME_ICONS = (
    '<svg class="i-sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/>'
    '<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>'
    '<svg class="i-moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z"/></svg>'
)
SEARCH_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>'


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def local(iso: str) -> dt.datetime:
    return dt.datetime.fromisoformat(iso).astimezone(AR)


class Lang:
    """Textos y formatos de un idioma."""

    def __init__(self, code: str):
        self.code = code
        self.t = LANGS[code]
        self.prefix = self.t["prefix"]

    def __getitem__(self, key: str):
        return self.t[key]

    def path(self, key: str = "home", extra: str = "") -> str:
        if key == "home":
            return self.prefix or "/"
        return f'{self.prefix}/{self.t["sec"][key][0]}{extra}'

    def file(self, key: str = "home", extra: str = "") -> str:
        if key == "home":
            return "en.html" if self.prefix else "index.html"
        return f'{self.path(key, extra).lstrip("/")}.html'

    def name(self, key: str) -> str:
        return self.t["sec"][key][1]

    def description(self, key: str) -> str:
        return self.t["sec"][key][2]

    def category(self, key: str) -> str:
        return self.t["categories"].get(key, key)

    def short_date(self, iso: str) -> str:
        when = local(iso)
        month = self.t["months"][when.month - 1][:3]
        return f"{when.day} {month}, {when:%H:%M}" if self.code == "es" else f"{month} {when.day}, {when:%H:%M}"

    def day(self, day: dt.date) -> str:
        weekday, month = self.t["days"][day.weekday()], self.t["months"][day.month - 1]
        if self.code == "es":
            return f"{weekday}, {day.day} de {month} de {day.year}"
        return f"{weekday}, {month} {day.day}, {day.year}"

    def date(self, iso_day: str) -> str:
        day = dt.date.fromisoformat(iso_day)
        month = self.t["months"][day.month - 1][:3]
        return f"{day.day} {month}" if self.code == "es" else f"{month} {day.day}"

    def month_name(self, month: str) -> str:
        year, number = month.split("-")
        name = self.t["months"][int(number) - 1]
        return self.t["month_name"].format(month=name.capitalize(), year=year)

    def time_tag(self, iso: str) -> str:
        return f'<time datetime="{esc(iso)}" data-rel>{esc(self.short_date(iso))}</time>'

    def topic(self, item: dict) -> str:
        return self.category(item["category"]) if item["category"] != "General" else self.t["regions"][item["region"]]


def region_chip(lang: Lang, item: dict) -> str:
    """Ficha de color con la región: se reconoce de un vistazo de dónde es cada nota."""
    return f'<span class="chip chip-{esc(item["region"])}">{esc(lang["regions"][item["region"]])}</span>'


def story(lang: Lang, item: dict, heading: str = "h3", summary: bool = True, css: str = "story") -> str:
    url = safe_url(item["url"])
    if not url:
        return ""
    item_lang = item.get("lang", "es")
    attr = f' lang="{esc(item_lang)}"' if item_lang != lang.code else ""
    flag = f'<span class="flag">{esc(lang["alert"])}</span>' if item["alert"] else ""
    topic = f'<span class="subject">{esc(lang.category(item["category"]))}</span> · ' if item["category"] != "General" else ""
    body = f'<p class="summary"{attr}>{esc(item["summary"])}</p>' if summary and item["summary"] else ""
    return (
        f'<article class="{css}" data-region="{esc(item["region"])}" data-category="{esc(item["category"])}" data-seen="{esc(item["first_seen"])}">'
        f'<p class="tags">{region_chip(lang, item)}{flag}</p>'
        f'<{heading}{attr}><a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(item["title"])}</a></{heading}>'
        f'{body}<p class="meta">{topic}{esc(item["source"])} <span class="when">· {lang.time_tag(item["published"])}</span></p></article>'
    )


def river(lang: Lang, items: list[dict]) -> str:
    groups: dict[dt.date, list[str]] = {}
    for item in items:
        groups.setdefault(local(item["published"]).date(), []).append(story(lang, item))
    return "".join(
        f'<section class="day-block"><h2 class="day" data-day="{day.isoformat()}">{esc(lang.day(day))}</h2>'
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

    subleads = take(pool, lambda i: i["summary"], 6)  # seis llenan la columna central a la altura de las laterales
    argentina = take(items, lambda i: i["region"] == "ar", 7)
    alerts = take(items, lambda i: i["alert"], 7)
    alerts += take(pool, lambda i: i["category"] in CRITICAL_TOPICS, 7 - len(alerts))
    return {"lead": lead, "subleads": subleads, "argentina": argentina, "alerts": alerts, "used": used}


def column(lang: Lang, title: str, items: list[dict], alert: bool = False) -> str:
    css = "column-title is-alert" if alert else "column-title"
    return f'<div class="column"><h2 class="{css}">{esc(title)}</h2>{"".join(story(lang, i, summary=False) for i in items)}</div>'


def front_html(lang: Lang, front: dict) -> str:
    subleads = "".join(story(lang, i) for i in front["subleads"])
    subleads_html = f'<div class="subleads">{subleads}</div>' if subleads else ""
    return (
        f'<section class="front" aria-label="{esc(lang["front"])}">'
        f'{column(lang, lang["col_ar"], front["argentina"])}'
        f'<div class="lead">{story(lang, front["lead"], heading="h2", css="lead-story")}{subleads_html}</div>'
        f'{column(lang, lang["col_alerts"], front["alerts"], alert=True)}</section>'
    )


def pulse(lang: Lang, items: list[dict], now: dt.datetime) -> str:
    """Barras de notas por día en los últimos 14 días, en SVG sin JavaScript."""
    today = now.astimezone(AR).date()
    days = [today - dt.timedelta(days=13 - n) for n in range(14)]
    counts = Counter(local(i["published"]).date() for i in items)
    peak = max([counts[d] for d in days] + [1])
    bars = []
    for index, day in enumerate(days):
        height = max(2, round(counts[day] / peak * 34)) if counts[day] else 2
        css = "bar today" if day == today else "bar"
        label = lang["pulse_day"].format(day=lang.date(day.isoformat()), n=counts[day])
        bars.append(
            f'<g><title>{esc(label)}</title><rect class="hit" x="{index * 12}" y="0" width="12" height="36"/>'
            f'<rect class="{css}" x="{index * 12 + 2}" y="{36 - height}" width="8" height="{height}"/></g>'
        )
    summary = lang["pulse_summary"].format(peak=peak, today=counts[today])
    return (
        f'<figure class="pulse-chart"><svg viewBox="0 0 168 36" role="img" aria-label="{esc(summary)}">{"".join(bars)}</svg>'
        f'<figcaption>{esc(lang["pulse_caption"].format(peak=peak))}</figcaption></figure>'
    )


def epss_cell(lang: Lang, entry: dict) -> str:
    value = entry.get("epss")
    if not isinstance(value, (int, float)):
        return '<span class="epss is-none">—</span>'
    css = "epss is-high" if value >= EPSS_HIGH else "epss"
    return f'<span class="{css}" title="{esc(lang["epss_hint"])}">{value * 100:.1f} %</span>'


def product_name(entry: dict) -> str:
    """«PHP Group» + «PHP» o «WordPress» + «WordPress Core» se leen mejor sin repetir el fabricante."""
    vendor, product = entry["vendor"].strip(), entry["product"].strip()
    first = vendor.split(" ")[0].casefold() if vendor else ""
    if not vendor or (first and product.casefold().startswith(first)):
        return product or vendor
    if product.casefold() in vendor.casefold():
        return vendor
    return f"{vendor} {product}".strip()


# Los roles mantienen la tabla legible para lectores de pantalla cuando en celular se muestra como fichas.
ROW_HEAD = '<th scope="row" role="rowheader">'


def table(heads: list[str], rows: str, label: str) -> str:
    cols = "".join(f'<th scope="col" role="columnheader">{esc(h)}</th>' for h in heads)
    return (f'<div class="table-wrap"><table class="vuln-table" role="table" aria-label="{esc(label)}">'
            f'<thead role="rowgroup"><tr role="row">{cols}</tr></thead><tbody role="rowgroup">{rows}</tbody></table></div>')


def cell(label: str, content: str, attrs: str = "") -> str:
    return f'<td role="cell" data-label="{esc(label)}"{attrs}>{content}</td>'


def kev_table(lang: Lang, entries: list[dict], compact: bool = False) -> str:
    foreign = ' lang="en"' if lang.code != "en" else ""
    rows = []
    for e in entries:
        tag = f'<span class="tag is-alert">{esc(lang["ransomware"])}</span>' if e["ransomware"] else ""
        link = (f'<a class="cve" href="{esc(e["url"])}" target="_blank" rel="noopener noreferrer" translate="no">'
                f'{esc(e["cve"])}</a>')
        added = f'<time datetime="{esc(e["added"])}">{esc(lang.date(e["added"]))}</time>'
        cells = [cell(lang["th_product"], esc(product_name(e)) + (tag if compact else ""), ' translate="no"')]
        if not compact:
            cells.append(cell(lang["th_flaw"], esc(e["name"]) + tag, foreign))
        cells.append(cell(lang["th_added"], added))
        if not compact:
            cells.append(cell(lang["th_due"], f'<span class="date">{esc(lang.date(e["due"]))}</span>' if e["due"] else "—"))
        cells.append(cell(lang["th_epss"], epss_cell(lang, e)))
        rows.append(f'<tr role="row">{ROW_HEAD}{link}</th>{"".join(cells)}</tr>')
    heads = [lang["th_cve"], lang["th_product"]] + ([] if compact else [lang["th_flaw"]]) + [lang["th_added"]]
    heads += ([] if compact else [lang["th_due"]]) + [lang["th_epss"]]
    return table(heads, "".join(rows), lang["kev_heading"])


def nvd_table(lang: Lang, entries: list[dict]) -> str:
    foreign = ' lang="en"' if lang.code != "en" else ""
    rows = "".join(
        f'<tr role="row">{ROW_HEAD}<a class="cve" href="{esc(e["url"])}" target="_blank" rel="noopener noreferrer" '
        f'translate="no">{esc(e["cve"])}</a></th>'
        + cell(lang["th_cvss"], f'<span class="score">{e["score"]:.1f}</span>')
        + cell(lang["th_desc"], esc(e["description"]), f' class="desc"{foreign}')
        + cell(lang["th_published"], lang.time_tag(e["published"]))
        + cell(lang["th_epss"], epss_cell(lang, e)) + "</tr>"
        for e in entries
    )
    heads = [lang["th_cve"], lang["th_cvss"], lang["th_desc"], lang["th_published"], lang["th_epss"]]
    return table(heads, rows, lang["nvd_heading"])


def json_ld(data: dict) -> str:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return f'<script type="application/ld+json">{text}</script>'


class Site:
    def __init__(self, data_dir: Path, source: Path, out: Path, site_url: str):
        self.data_dir, self.source, self.out = data_dir, source, out
        self.url = site_url.rstrip("/")
        self.latest = json.loads((data_dir / "latest.json").read_text(encoding="utf-8"))
        self.items = [i for i in self.latest["items"] if safe_url(i["url"])]
        self.months = self.latest["months"]
        self.generated = self.latest["generated"]
        self.now = dt.datetime.fromisoformat(self.generated)
        self.year = self.now.astimezone(AR).year
        vulns_path = data_dir / "vulns.json"
        self.vulns = json.loads(vulns_path.read_text(encoding="utf-8")) if vulns_path.is_file() else {}
        self.assets: dict[str, str] = {}
        self.pages: list[tuple[str, dict[str, str]]] = []

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

    def absolute(self, path: str) -> str:
        return self.url + (path if path != "/" else "/")

    # --- Piezas comunes ---
    def status_line(self, lang: Lang) -> str:
        day_ago = self.now - dt.timedelta(hours=24)
        alerts = sum(1 for i in self.items if i["alert"] and dt.datetime.fromisoformat(i["published"]) >= day_ago)
        sources = self.latest["sources"]
        healthy = sum(1 for s in sources if s["ok"])
        one, many = lang["alerts_24h"]
        word = one if alerts == 1 else many
        return (f'<span class="status">{esc(lang["updated"])} {lang.time_tag(self.generated)}<span class="extra"> · '
                f'<strong>{alerts} {word}</strong> {esc(lang["in_24h"])} · {healthy}/{len(sources)} {esc(lang["sources"])}</span></span>')

    def wire(self, lang: Lang) -> str:
        """Barra roja de la última alerta, con la actividad de los últimos 14 días a la derecha."""
        latest = next((i for i in self.items if i["alert"]), None)
        chart = pulse(lang, self.items, self.now)
        if not latest:
            return f'<aside class="wire" aria-label="{esc(lang["activity"])}">{chart}</aside>'
        attr = f' lang="{esc(latest.get("lang", "es"))}"' if latest.get("lang", "es") != lang.code else ""
        return (
            f'<aside class="wire" aria-label="{esc(lang["last_alert_label"])}"><div class="wire-news">'
            f'<span class="wire-label"><span class="pulse" aria-hidden="true"></span>{esc(lang["latest_alert"])}</span>'
            f'<a{attr} href="{esc(safe_url(latest["url"]))}" target="_blank" rel="noopener noreferrer">{esc(latest["title"])}</a>'
            f'<span class="wire-meta">{lang.time_tag(latest["published"])}</span></div>{chart}</aside>'
        )

    def nav(self, lang: Lang, current: str) -> str:
        entries = [("home", lang["home"])] + [(k, lang.name(k)) for k in NEWS_SECTIONS + ["vulns"]]
        links = "".join(
            f'<a href="{lang.path(key)}"{" aria-current=\"page\"" if key == current else ""}>{esc(name)}</a>'
            for key, name in entries
        )
        return f'<nav class="sections" aria-label="{esc(lang["sections_label"])}">{links}</nav>'

    def tools(self, lang: Lang, items: list[dict]) -> str:
        categories = sorted({i["category"] for i in items}, key=lambda c: lang.category(c).casefold())
        options = "".join(f'<option value="{esc(c)}">{esc(lang.category(c))}</option>' for c in categories)
        return (
            '<form class="tools" role="search" action="#" autocomplete="off">'
            f'<label class="search"><span class="sr">{esc(lang["search_label"])}</span>{SEARCH_ICON}'
            f'<input id="query" type="search" placeholder="{esc(lang["search_ph"])}" enterkeyhint="search" spellcheck="false"></label>'
            f'<label class="topic"><span class="sr">{esc(lang["topic_label"])}</span>'
            f'<select id="category"><option value="">{esc(lang["all_topics"])}</option>{options}</select></label>'
            f'<button class="sr" type="submit">{esc(lang["search_btn"])}</button></form>'
        )

    def footer(self, lang: Lang) -> str:
        sources = "".join(
            f'<li class="{"ok" if s["ok"] else "down"}">{esc(lang["ok"] if s["ok"] else lang["down"])} · {esc(s["name"])}</li>'
            for s in self.latest["sources"] + self.vulns.get("sources", [])
        )
        sections = "".join(f'<li><a href="{lang.path(k)}">{esc(lang.name(k))}</a></li>' for k in NEWS_SECTIONS + ["vulns"])
        return (
            '<footer class="colophon"><div class="foot-grid">'
            f'<div class="foot-brand"><a class="foot-name" href="{OWNER_URL}" rel="noopener">{BRAND_MARK}'
            f'<span translate="no">{OWNER}</span></a>'
            f'<p>{esc(lang["about"].format(owner=OWNER))}</p></div>'
            f'<nav class="foot-col" aria-label="{esc(lang["diary"])}"><h2>{esc(lang["diary"])}</h2><ul>{sections}'
            f'<li><a href="{lang.path("archive")}">{esc(lang["archive"])}</a></li><li><a href="/feed.xml">RSS</a></li></ul></nav>'
            f'<div class="foot-col"><h2>{esc(lang["contact"])}</h2><ul>'
            f'<li><a href="{OWNER_URL}" rel="noopener">{esc(lang["portfolio"])} <span class="arrow" aria-hidden="true">↗</span></a></li>'
            f'<li><a href="mailto:{OWNER_EMAIL}">{OWNER_EMAIL}</a></li></ul></div></div>'
            f'<details><summary>{esc(lang["install"])}</summary><p>{lang["install_text"]}</p></details>'
            f'<details><summary>{esc(lang["status"])}</summary><ul class="source-list">{sources}</ul></details>'
            f'<div class="legal"><p>© {self.year} <a href="{OWNER_URL}" rel="noopener">{OWNER}</a>. {esc(lang["rights"])} '
            f'{esc(lang["role"])}</p><p>{esc(lang["credits"])} {esc(lang["nvd_notice"])}</p></div>'
            '</footer>'
        )

    def page(self, lang: Lang, key: str, title: str, description: str, content: str, *,
             extra: str = "", items: list[dict] | None = None, heading: str | None = None,
             extra_ld: list[dict] | None = None, indexable: bool = True, search: bool = True) -> None:
        """key identifica la página en ambos idiomas; extra agrega un sufijo, como el mes del archivo."""
        path = lang.path(key, extra)
        alternates = {code: Lang(code).path(key, extra) for code in LANGS}
        other = Lang("en" if lang.code == "es" else "es")
        is_home = key == "home"
        canonical = self.absolute(path)
        brand = f'<a href="{lang.path()}" aria-label="{SITE_NAME}, {esc(lang["home"])}"><span class="side">Cibe</span><span class="rr" aria-hidden="true"><span class="r-flip">R</span><span>R</span></span><span class="side">adar</span></a>'
        brand_tag = "h1" if is_home else "p"
        intro = f'<header class="page-head"><h1>{esc(heading)}</h1><p>{esc(description)}</p></header>' if heading else ""
        owner = {"@type": "Person", "name": OWNER, "url": OWNER_URL, "email": f"mailto:{OWNER_EMAIL}"}
        website = {"@context": "https://schema.org", "@type": "WebSite", "name": SITE_NAME, "url": self.absolute(lang.path()),
                   "inLanguage": lang["html"], "description": lang["home_description"], "author": owner, "publisher": owner,
                   "copyrightHolder": owner, "copyrightYear": self.year}
        ld = "".join(json_ld(d) for d in [website, *(extra_ld or [])])
        robots = "index,follow,max-image-preview:large,max-snippet:-1" if indexable else "noindex"
        hreflang = "".join(
            f'<link rel="alternate" hreflang="{LANGS[code]["html"]}" href="{esc(self.absolute(p))}">' for code, p in alternates.items()
        ) + f'<link rel="alternate" hreflang="x-default" href="{esc(self.absolute(alternates["es"]))}">'
        current = "home" if is_home else key
        tools = self.tools(lang, items if items is not None else self.items) if search else ""
        document = f'''<!DOCTYPE html>
<html lang="{lang["html"]}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<meta name="robots" content="{robots}">
<link rel="canonical" href="{esc(canonical)}">
{hreflang if indexable else ""}
<meta name="theme-color" content="#ffffff">
<meta name="author" content="{OWNER}">
<meta name="copyright" content="© {self.year} {OWNER}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:locale" content="{lang["og"]}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:image" content="{esc(self.url)}/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Ciber Radar">
<meta name="twitter:card" content="summary_large_image">
<link rel="alternate" type="application/rss+xml" title="{SITE_NAME}" href="/feed.xml">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="icon" href="/favicon.ico" sizes="32x32">
<link rel="icon" href="/icons/icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png">
<link rel="preload" href="/fonts/schibsted-grotesk-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/dm-serif-display-latin-400-normal.woff2" as="font" type="font/woff2" crossorigin>
<script src="{self.assets["theme.js"]}"></script>
<link rel="stylesheet" href="{self.assets["styles.css"]}">
<script src="{self.assets["app.js"]}" defer></script>
{ld}
</head>
<body>
<a class="skip" href="#contenido">{esc(lang["skip"])}</a>
<header>
<div class="topbar"><span class="date">{esc(lang["today_label"])} <span id="today">{esc(lang.day(self.now.astimezone(AR).date()))}</span></span><div class="topbar-right">{self.status_line(lang)}<a class="lang-switch" href="{other.path(key, extra) if indexable else other.path()}" hreflang="{other["html"]}" lang="{other["html"]}" aria-label="{esc(lang["lang_switch_label"])}">{esc(lang["lang_switch"])}</a><button class="theme-toggle" type="button" id="theme" aria-label="{esc(lang["theme"])}">{THEME_ICONS}</button></div></div>
<div class="masthead">
<{brand_tag} class="brand" translate="no">{brand}</{brand_tag}>
<p class="motto">{esc(lang["masthead_sub"])}</p>
</div>
</header>
{self.nav(lang, current)}
{self.wire(lang)}
{tools}
<main id="contenido" data-view="{esc(key if key in NEWS_SECTIONS else "")}">
<div id="page">{intro}{content}</div>
<section id="results" aria-live="polite" hidden></section>
</main>
{self.footer(lang)}
</body>
</html>
'''
        self.write(lang.file(key, extra), document)
        if indexable:
            self.pages.append((path, alternates))

    def item_list(self, lang: Lang, name: str, items: list[dict], path: str) -> dict:
        return {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": name,
            "url": self.absolute(path),
            "inLanguage": lang["html"],
            "mainEntity": {
                "@type": "ItemList",
                "itemListElement": [
                    {"@type": "ListItem", "position": n, "url": i["url"], "name": i["title"]}
                    for n, i in enumerate(items[:20], start=1)
                ],
            },
        }

    def bars(self, rows: list[tuple[str, int]], unit: tuple[str, str]) -> str:
        """Lista ordenada con una barra por fila. La barra es un <progress>: no necesita estilos en línea."""
        peak = max([n for _, n in rows] + [1])
        return '<ol class="bars">' + "".join(
            f'<li><span class="bar-name">{esc(name)}</span><progress max="{peak}" value="{n}" aria-hidden="true"></progress>'
            f'<span class="bar-n">{n}<span class="sr"> {esc(unit[0] if n == 1 else unit[1])}</span></span></li>'
            for name, n in rows
        ) + "</ol>"

    def country_counts(self) -> list[tuple[str, int]]:
        counts: Counter[str] = Counter()
        for item in self.items:
            text = " ".join(re.sub(r"[^a-z0-9]+", " ", norm(f'{item["title"]} {item["summary"]}')).split())
            found = {code for code, pattern in COUNTRY_PATTERNS.items() if pattern.search(text)}
            if item["region"] == "ar":
                found.add("ar")
            counts.update(found)
        return counts.most_common()

    def world_map(self, lang: Lang, counts: list[tuple[str, int]]) -> str:
        name = 0 if lang.code == "es" else 1
        peak = max([n for _, n in counts] + [1])
        spots = []
        for code, n in sorted(counts, key=lambda c: -c[1]):  # los grandes primero, así no tapan a los chicos
            country = COUNTRIES[code]
            x = (country[2] + 180) / 360 * MAP_W
            y = (MAP_TOP - country[3]) / (MAP_TOP - MAP_BOTTOM) * MAP_H
            radius = 5 + 27 * math.sqrt(n / peak)
            unit = lang["note_count"][0 if n == 1 else 1]
            spots.append(f'<circle class="spot" cx="{x:.0f}" cy="{y:.0f}" r="{radius:.1f}"><title>{esc(country[name])}: {n} {esc(unit)}</title></circle>')
        top = ", ".join(f"{COUNTRIES[c][name]} ({n})" for c, n in counts[:5])
        return (
            f'<figure class="map"><svg viewBox="0 0 {MAP_W} {MAP_H}" role="img" aria-label="{esc(lang["map_alt"].format(top=top))}">'
            '<defs><pattern id="halftone" width="5" height="5" patternUnits="userSpaceOnUse"><circle class="grain" cx="2.5" cy="2.5" r="1.25"/></pattern></defs>'
            f'<path class="land" fill="url(#halftone)" d="{WORLD_LAND}"/>{"".join(spots)}</svg>'
            f'<figcaption>{esc(lang["map_caption"])}</figcaption></figure>'
        )

    def home_data(self, lang: Lang) -> str:
        """El radar en datos: mapa de países nombrados, temas, notas por día y tipo de fuente."""
        name = 0 if lang.code == "es" else 1
        counts = self.country_counts()
        if not counts:
            return ""
        unit = lang["note_count"]
        countries = [(COUNTRIES[c][name], n) for c, n in counts[:8]]
        topics = Counter(i["category"] for i in self.items if i["category"] != "General").most_common(7)
        kinds = source_kinds()
        by_kind = Counter(kinds.get(i["source"], "prensa") for i in self.items)
        trust = [(lang["trust_kinds"][k], by_kind[k]) for k in TRUST_ORDER if by_kind[k]]
        feeds = self.latest["sources"]
        note = lang["trust_note"].format(ok=sum(1 for f in feeds if f["ok"]), total=len(feeds))
        return (
            f'<section class="data" aria-labelledby="data-title">{self.block_head(lang["data_title"], "data-title")}'
            f'<p class="block-sub">{esc(lang["data_sub"].format(n=len(self.items)))}</p>'
            f'<div class="data-top"><div class="panel"><h3>{esc(lang["map_title"])}</h3>{self.world_map(lang, counts)}</div>'
            f'<div class="panel"><h3>{esc(lang["rank_title"])}</h3>{self.bars(countries, unit)}</div></div>'
            f'<div class="data-row"><div class="panel"><h3>{esc(lang["topics_title"])}</h3>'
            f'{self.bars([(lang.category(c), n) for c, n in topics], unit)}</div>'
            f'<div class="panel"><h3>{esc(lang["days_title"])}</h3>{pulse(lang, self.items, self.now)}</div>'
            f'<div class="panel"><h3>{esc(lang["trust_title"])}</h3>{self.bars(trust, unit)}<p class="panel-note">{esc(note)}</p></div>'
            '</div></section>'
        )

    def block_head(self, title: str, ident: str, link: str = "", link_text: str = "") -> str:
        more = f'<a class="block-more" href="{link}">{esc(link_text)} »</a>' if link else ""
        return f'<div class="block-head"><h2 id="{ident}">{esc(title)}</h2>{more}</div>'

    def home_sections(self, lang: Lang, used: set[str]) -> str:
        """Un bloque por región con sus cuatro notas más nuevas que no estén ya en la tapa."""
        blocks = []
        by_id = {i["id"]: i for i in self.items}
        titles = [set(title_words(by_id[i]["title"])) for i in used if i in by_id]  # no repetir la misma noticia de otra fuente
        for key in ("ar", "latam", "mundo"):
            picked: list[dict] = []
            for item in self.items:
                words = set(title_words(item["title"]))
                if item["region"] != key or item["id"] in used or any(same_story(words, seen) for seen in titles):
                    continue
                picked.append(item)
                titles.append(words)
                if len(picked) == 4:
                    break
            if len(picked) < 4:  # una fila incompleta queda coja: esa región ya tiene su columna o su sección
                continue
            used.update(i["id"] for i in picked)
            blocks.append(
                f'<section class="block" aria-labelledby="block-{key}">'
                f'{self.block_head(lang.name(key), f"block-{key}", lang.path(key), lang["view_all"])}'
                f'<div class="block-grid">{"".join(story(lang, i) for i in picked)}</div></section>'
            )
        return "".join(blocks)

    def more_link(self, lang: Lang) -> str:
        month = self.months[0] if self.months else ""
        if not month:
            return ""
        return f'<p class="more"><a href="{lang.path("archive", "/" + month)}">{esc(lang["more_month"])}</a></p>'

    def home_vulns(self, lang: Lang) -> str:
        kev = self.vulns.get("kev", [])[:KEV_ON_HOME]
        if not kev:
            return ""
        return (
            f'<section class="vuln-strip" aria-labelledby="radar-title">'
            f'{self.block_head(lang["home_kev"], "radar-title", lang.path("vulns"), lang["home_kev_more"])}'
            f'<p class="strip-sub">{esc(lang["kev_sub"])}</p>{kev_table(lang, kev, compact=True)}</section>'
        )

    # --- Páginas ---
    def build_home(self, lang: Lang) -> None:
        front = pick_front(self.items, self.now)
        used = set(front["used"])
        sections = self.home_sections(lang, used)
        rest = [i for i in self.items if i["id"] not in used][:RIVER_ON_HOME]
        latest = (f'<section class="latest" aria-labelledby="latest-title">{self.block_head(lang["latest_title"], "latest-title")}'
                  f'<div class="river">{river(lang, rest)}</div></section>')
        content = front_html(lang, front) + self.home_data(lang) + sections + self.home_vulns(lang) + latest + self.more_link(lang)
        self.page(lang, "home", lang["home_title"], lang["home_description"], content,
                  extra_ld=[self.item_list(lang, lang["home_title"], self.items, lang.path())])

    def build_sections(self, lang: Lang) -> None:
        for key in NEWS_SECTIONS:
            items = [i for i in self.items if (i["alert"] if key == "alert" else i["region"] == key)]
            shown = items[:ITEMS_PER_SECTION]
            empty = f'<p class="notice">{esc(lang["empty"])}</p>'
            content = (f'<div class="river">{river(lang, shown)}</div>' if shown else empty) + self.more_link(lang)
            title = f'{lang["section_title"].format(name=lang.name(key))} | {SITE_NAME}'
            self.page(lang, key, title, lang.description(key), content, items=shown, heading=lang.name(key),
                      extra_ld=[self.item_list(lang, title, shown, lang.path(key))])

    def build_vulns(self, lang: Lang) -> None:
        kev, critical = self.vulns.get("kev", []), self.vulns.get("critical", [])
        if not kev and not critical:
            body = f'<p class="notice">{esc(lang["no_vulns"])}</p>'
        else:
            stats = lang["vuln_stats"].format(kev=len(kev), nvd=len(critical), total=self.vulns.get("kev_total", 0))
            updated = self.vulns.get("generated")
            stamp = f' · {esc(lang["updated"])} {lang.time_tag(updated)}' if updated else ""
            body = (
                f'<p class="vuln-stats">{esc(stats)}{stamp}</p>'
                f'<form class="tools" role="search" action="#" autocomplete="off"><label class="search">'
                f'<span class="sr">{esc(lang["vuln_filter"])}</span>{SEARCH_ICON}'
                f'<input id="vuln-filter" type="search" placeholder="{esc(lang["vuln_filter_ph"])}" '
                f'enterkeyhint="search" spellcheck="false"></label></form>'
                f'<p id="vuln-empty" class="notice" role="status" hidden>{esc(lang["vuln_none"])}</p>'
                f'<section class="vuln-block" aria-labelledby="kev-title"><h2 id="kev-title" class="day">{esc(lang["kev_heading"])}</h2>'
                f'<p class="strip-sub">{esc(lang["kev_sub"])}</p>{kev_table(lang, kev)}</section>'
                f'<section class="vuln-block" aria-labelledby="nvd-title"><h2 id="nvd-title" class="day">{esc(lang["nvd_heading"])}</h2>'
                f'<p class="strip-sub">{esc(lang["nvd_sub"])}</p>{nvd_table(lang, critical)}</section>'
                f'<p class="vuln-sources">{esc(lang["vuln_sources"])} {esc(lang["nvd_notice"])}</p>'
            )
        self.page(lang, "vulns", f'{lang["vulns_title"]} | {SITE_NAME}', lang["vulns_desc"], body,
                  heading=lang["vulns"], search=False)

    def build_archive(self, lang: Lang) -> None:
        rows = []
        for month in self.months:
            items = json.loads((self.data_dir / f"{month}.json").read_text(encoding="utf-8"))
            items = [i for i in items if safe_url(i["url"])]
            name = lang.month_name(month)
            rows.append(f'<li><a href="{lang.path("archive", "/" + month)}">{esc(name)}</a><span>{len(items)} {esc(lang["notes"])}</span></li>')
            self.page(lang, "archive", f'{lang["archive_month_title"].format(name=name)} | {SITE_NAME}',
                      lang["archive_month_desc"].format(name=name), f'<div class="river">{river(lang, items)}</div>',
                      extra="/" + month, items=items, heading=name)
        self.page(lang, "archive", f'{lang["archive"]} | {SITE_NAME}', lang["archive_desc"],
                  f'<ul class="archive">{"".join(rows)}</ul>', items=[], heading=lang["archive"])

    def build_404(self) -> None:
        es, en = Lang("es"), Lang("en")
        body = (f'<p class="notice">{esc(es["not_found_text"])} <a href="/">{esc(es["back_home"])}</a>.</p>'
                f'<p class="notice" lang="en">{esc(en["not_found_text"])} <a href="/en">{esc(en["back_home"])}</a>.</p>')
        self.page(es, "notfound", f'{es["not_found"]} | {SITE_NAME}', es["not_found_text"], body,
                  items=[], heading=es["not_found"], indexable=False)

    def build_feed(self) -> None:
        es = Lang("es")
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
            f'<title>{SITE_NAME}</title><link>{xml_escape(self.url)}/</link><description>{xml_escape(es["home_description"])}</description>'
            f'<language>es-AR</language><copyright>© {self.year} {OWNER}</copyright><lastBuildDate>{built}</lastBuildDate>'
            f'<atom:link href="{xml_escape(self.url)}/feed.xml" rel="self" type="application/rss+xml"/>{"".join(entries)}</channel></rss>\n',
        )

    def build_discovery(self) -> None:
        stamp = self.now.date().isoformat()
        urls = []
        for path, alternates in self.pages:
            links = "".join(
                f'<xhtml:link rel="alternate" hreflang="{LANGS[code]["html"]}" href="{xml_escape(self.absolute(p))}"/>'
                for code, p in alternates.items()
            )
            urls.append(f"<url><loc>{xml_escape(self.absolute(path))}</loc><lastmod>{stamp}</lastmod>{links}</url>")
        self.write(
            "sitemap.xml",
            '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            f'xmlns:xhtml="http://www.w3.org/1999/xhtml">{"".join(urls)}</urlset>\n',
        )
        self.write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {self.url}/sitemap.xml\n")
        expires = (self.now + dt.timedelta(days=330)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.write(
            ".well-known/security.txt",
            f"Contact: mailto:{OWNER_EMAIL}\nExpires: {expires}\n"
            f"Preferred-Languages: es, en\nCanonical: {self.url}/.well-known/security.txt\n",
        )

    def build_static(self) -> None:
        for name in ("fonts", "icons"):
            shutil.copytree(self.source / name, self.out / name)
        for name in ("og.png", "manifest.webmanifest", "favicon.ico"):
            shutil.copy2(self.source / name, self.out / name)
        self.write("data/latest.json", json.dumps({"items": self.items}, ensure_ascii=False, separators=(",", ":")))
        precache = ["/", "/en", self.assets["styles.css"], self.assets["app.js"], self.assets["theme.js"],
                    "/data/latest.json", "/icons/icon-192.png"]
        precache += sorted(f"/fonts/{p.name}" for p in (self.source / "fonts").glob("*.woff2"))
        version = hashlib.sha256("".join(precache).encode()).hexdigest()[:12]
        worker = (self.source / "sw.js").read_text(encoding="utf-8")
        self.write("sw.js", worker.replace("__PRECACHE__", json.dumps(precache)).replace("__VERSION__", version))

    def build(self) -> None:
        if self.out.exists():
            shutil.rmtree(self.out)
        self.out.mkdir(parents=True)
        for asset in ("styles.css", "app.js", "theme.js"):
            self.fingerprint(asset)
        for code in LANGS:
            lang = Lang(code)
            self.build_home(lang)
            self.build_sections(lang)
            self.build_vulns(lang)
            self.build_archive(lang)
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
    Site(args.data, args.source, args.out, site_url).build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
