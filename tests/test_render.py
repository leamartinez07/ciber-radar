import json
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "collector"))

import render  # noqa: E402

ATTACK = '<script>alert(1)</script>"><img src=x onerror=alert(2)>'


def item(n, **extra):
    base = {
        "id": f"id{n}", "title": f"Noticia número {n} sobre seguridad {'alfa beta gamma delta'.split()[n % 4]} {n * 7}",
        "url": f"https://a.test/{n}", "source": "Fuente", "summary": "Resumen breve de la nota.",
        "region": "ar", "category": "General", "alert": False,
        "published": f"2026-11-{(n % 9) + 1:02d}T10:00:00+00:00",
        "first_seen": "2026-11-10T10:00:00+00:00",
    }
    return {**base, **extra}


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        base = Path(cls.temp.name)
        data, cls.out = base / "data", base / "public"
        data.mkdir()
        items = [item(n) for n in range(1, 20)]
        items.append(item(30, id="evil", title=ATTACK, source=ATTACK, summary=ATTACK, alert=True,
                          published="2026-11-10T09:00:00+00:00"))
        items.append(item(31, id="badlink", url="javascript:alert(3)", title="Enlace peligroso de prueba"))
        items.append(item(32, id="english", lang="en", title="Critical bug exploited in the wild today",
                          image="https://img.test/foto.jpg"))
        items.append(item(33, id="traducida", lang="en", title="Original English headline about ransomware gangs",
                          tr={"es": {"title": "Título traducido sobre bandas de ransomware", "summary": "Bajada traducida.",
                                     "body": ["Primer párrafo del resumen propio.", "Segundo párrafo."]},
                              "en": {"title": "Ransomware gangs, in our own words", "summary": "Our dek.",
                                     "body": ["First paragraph of our summary."]}}))
        items.append(item(34, id="oficial", source="CISA", lang="en", title="Agency adds two exploited flaws to catalog",
                          body=[["h", "Subtítulo oficial"], ["p", "Texto completo del aviso oficial."], ["li", "CVE-2026-1"]],
                          reuse="Dominio público: obra del gobierno de EE. UU."))
        items.sort(key=lambda i: i["published"], reverse=True)
        (data / "2026-11.json").write_text(json.dumps(items), encoding="utf-8")
        latest = {
            "generated": "2026-11-10T12:00:00+00:00",
            "sources": [{"name": "Buena", "ok": True, "new": 1, "error": ""}, {"name": "Mala", "ok": False, "new": 0, "error": "URLError"}],
            "months": ["2026-11"],
            "items": items,
        }
        (data / "latest.json").write_text(json.dumps(latest), encoding="utf-8")
        vulns = {
            "generated": "2026-11-10T11:00:00+00:00", "kev_total": 1500,
            "kev": [{"cve": "CVE-2026-1111", "vendor": ATTACK, "product": "Router", "name": ATTACK, "description": ATTACK,
                     "added": "2026-11-09", "due": "2026-11-30", "ransomware": True,
                     "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-1111", "epss": 0.42, "percentile": 0.98}],
            "critical": [{"cve": "CVE-2026-3333", "score": 9.8, "cvss": "3.1", "description": ATTACK,
                          "published": "2026-11-10T01:00:00+00:00", "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-3333",
                          "epss": None, "percentile": None}],
            "sources": [{"name": "CISA KEV", "ok": True, "error": ""}],
        }
        (data / "vulns.json").write_text(json.dumps(vulns), encoding="utf-8")
        render.Site(data, ROOT / "site", cls.out, "https://radar.test").build()
        cls.home = (cls.out / "index.html").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def pages(self):
        return list(self.out.rglob("*.html"))

    def test_expected_pages_exist(self):
        for name in ("index", "argentina", "latinoamerica", "mundo", "alertas", "vulnerabilidades", "archivo",
                     "archivo/2026-11", "404", "en", "en/argentina", "en/latin-america", "en/world", "en/alerts",
                     "en/vulnerabilities", "en/archive", "en/archive/2026-11"):
            self.assertTrue((self.out / f"{name}.html").is_file(), name)

    def test_feed_text_is_escaped_everywhere(self):
        for path in self.pages():
            page = path.read_text(encoding="utf-8")
            self.assertNotIn("<script>alert", page, path)
            self.assertNotIn("<img src=x", page, path)

    def test_json_ld_cannot_close_its_script(self):
        blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', self.home, re.S)
        self.assertEqual(len(blocks), 2)
        for block in blocks:
            self.assertNotIn("<", block)
            json.loads(block)

    def test_unsafe_links_are_dropped(self):
        for path in self.pages():
            self.assertNotIn("javascript:", path.read_text(encoding="utf-8"), path)
        index = json.loads((self.out / "data/latest.json").read_text(encoding="utf-8"))
        self.assertNotIn("badlink", [i["id"] for i in index["items"]])

    def test_every_page_has_one_h1_and_a_canonical(self):
        for path in self.pages():
            page = path.read_text(encoding="utf-8")
            self.assertEqual(len(re.findall(r"<h1[ >]", page)), 1, path)
            self.assertEqual(len(re.findall(r'rel="canonical"', page)), 1, path)

    def test_assets_are_fingerprinted_and_exist(self):
        names = re.findall(r'(?:href|src)="(/assets/[^"]+)"', self.home)
        self.assertEqual(len(names), 3)
        for name in names:
            self.assertRegex(name, r"\.[0-9a-f]{12}\.(css|js)$")
            self.assertTrue((self.out / name.lstrip("/")).is_file())

    def test_no_inline_scripts_or_styles(self):
        for path in self.pages():
            page = path.read_text(encoding="utf-8")
            self.assertNotRegex(page, r"<script(?![^>]*(?:src=|application/ld\+json))")
            self.assertNotRegex(page, r"<style|\sstyle=|\son[a-z]+=\"")

    def note(self, path):
        return (self.out / f"{path}.html").read_text(encoding="utf-8")

    def test_titles_open_the_note_inside_the_site(self):
        self.assertIn('href="/nota/id1"', (self.out / "argentina.html").read_text(encoding="utf-8"))
        self.assertIn('href="/en/news/id1"', (self.out / "en/argentina.html").read_text(encoding="utf-8"))
        self.assertTrue((self.out / "nota/id1.html").is_file())
        self.assertTrue((self.out / "en/news/id1.html").is_file())

    def test_note_has_source_link_back_and_related(self):
        page = self.note("nota/english")
        self.assertIn("data-back", page)
        self.assertIn('class="note-out" href="https://a.test/32" target="_blank" rel="noopener noreferrer"', page)
        self.assertIn("De dónde es esta noticia", page)
        self.assertIn('src="https://img.test/foto.jpg" alt="" referrerpolicy="no-referrer"', page)
        self.assertIn("Imagen: Fuente", page)
        self.assertIn('href="/en/news/english"', page)  # el cambio de idioma lleva a la misma nota
        self.assertIn("Notas similares", page)

    def test_note_with_only_the_outlet_excerpt_is_not_indexed(self):
        page = self.note("nota/id1")
        self.assertIn('content="noindex,follow"', page)
        self.assertIn("Extracto publicado por Fuente", page)
        self.assertNotIn("/nota/id1<", (self.out / "sitemap.xml").read_text(encoding="utf-8"))

    def test_translation_is_shown_in_each_language(self):
        self.assertIn("Título traducido sobre bandas de ransomware", (self.out / "argentina.html").read_text(encoding="utf-8"))
        es, en = self.note("nota/traducida"), self.note("en/news/traducida")
        self.assertIn("Primer párrafo del resumen propio.", es)
        self.assertIn("Resumen escrito por Ciber Radar", es)
        self.assertIn("First paragraph of our summary.", en)
        self.assertIn('content="index,follow', es)
        self.assertIn("/nota/traducida<", (self.out / "sitemap.xml").read_text(encoding="utf-8"))

    def test_licensed_full_text(self):
        page = self.note("nota/oficial")
        self.assertIn("<h2>Subtítulo oficial</h2>", page)
        self.assertIn('<p class="li">CVE-2026-1</p>', page)
        self.assertIn("Texto completo publicado por CISA. Dominio público", page)

    def test_search_index_is_light(self):
        index = {i["id"]: i for i in json.loads((self.out / "data/latest.json").read_text(encoding="utf-8"))["items"]}
        self.assertEqual(index["id1"]["p"], 1)
        self.assertNotIn("body", index["oficial"])
        self.assertNotIn("body", index["traducida"]["tr"]["es"])
        self.assertEqual(index["traducida"]["tr"]["es"]["title"], "Título traducido sobre bandas de ransomware")

    def test_foreign_titles_are_marked(self):
        self.assertIn('<h3 lang="en">', (self.out / "argentina.html").read_text(encoding="utf-8"))
        english = (self.out / "en/argentina.html").read_text(encoding="utf-8")
        self.assertNotIn('<h3 lang="en">', english)
        self.assertIn('<h3 lang="es">', english)

    def test_xml_files_parse(self):
        for name in ("feed.xml", "sitemap.xml"):
            ET.fromstring((self.out / name).read_bytes())

    def test_sitemap_skips_404(self):
        sitemap = (self.out / "sitemap.xml").read_text(encoding="utf-8")
        self.assertIn("https://radar.test/argentina<", sitemap)
        self.assertNotIn("404", sitemap)

    def test_worker_has_precache_list(self):
        worker = (self.out / "sw.js").read_text(encoding="utf-8")
        self.assertNotIn("__", worker)
        self.assertIn("/data/latest.json", worker)

    def test_font_urls_are_absolute(self):
        css = (ROOT / "site/styles.css").read_text(encoding="utf-8")
        urls = re.findall(r'url\("([^"]+)"\)', css)
        self.assertTrue(urls)
        for url in urls:
            self.assertTrue((self.out / url.lstrip("/")).is_file(), url)

    def test_deploy_ignore_is_anchored_to_the_root(self):
        # Sin la barra inicial, "data" también excluye public/data y rompe búsqueda y offline.
        rules = (ROOT / ".vercelignore").read_text(encoding="utf-8").split()
        self.assertTrue(rules)
        for rule in rules:
            self.assertTrue(rule.startswith("/"), rule)

    def test_footer_credits_the_owner(self):
        for path in self.pages():
            page = path.read_text(encoding="utf-8")
            self.assertIn(f"© 2026", page, path)
            self.assertIn(render.OWNER, page, path)
            self.assertIn(f'href="mailto:{render.OWNER_EMAIL}"', page, path)
            self.assertIn(f'href="{render.OWNER_URL}"', page, path)

    def test_theme_script_runs_before_paint(self):
        head = self.home.split("</head>")[0]
        theme = re.search(r'<script src="(/assets/theme\.[0-9a-f]{12}\.js)"></script>', head)
        self.assertIsNotNone(theme)
        self.assertLess(head.index(theme.group(0)), head.index('rel="stylesheet"'))

    def test_nav_marks_only_the_current_section(self):
        for name, label in (("index", "Portada"), ("argentina", "Argentina"), ("archivo", None), ("404", None)):
            page = (self.out / f"{name}.html").read_text(encoding="utf-8")
            current = re.findall(r'aria-current="page">([^<]+)<', page)
            self.assertEqual(current, [label] if label else [], name)

    def test_languages_link_to_each_other(self):
        for name, lang, twin in (("argentina", "es-AR", "/en/argentina"), ("en/world", "en", "/mundo"),
                                 ("archivo/2026-11", "es-AR", "/en/archive/2026-11"), ("en", "en", "https://radar.test/")):
            page = (self.out / f"{name}.html").read_text(encoding="utf-8")
            self.assertIn(f'<html lang="{lang}">', page, name)
            self.assertIn('hreflang="x-default"', page, name)
            self.assertIn(twin, page, name)

    def test_english_interface(self):
        page = (self.out / "en.html").read_text(encoding="utf-8")
        self.assertIn("Vulnerability radar", page)
        self.assertIn("All rights reserved.", page)
        self.assertNotIn("Portada", page)

    def test_vulnerability_page(self):
        page = (self.out / "vulnerabilidades.html").read_text(encoding="utf-8")
        self.assertIn("CVE-2026-1111", page)
        self.assertIn("CVE-2026-3333", page)
        self.assertIn("42.0", page)
        self.assertIn("no lo respalda", page)
        self.assertIn('id="vuln-filter"', page)
        self.assertEqual(page.count('role="rowheader"'), 2)

    def test_product_name_does_not_repeat_the_vendor(self):
        for vendor, product, shown in (("PHP Group", "PHP", "PHP"), ("WordPress", "WordPress Core", "WordPress Core"),
                                       ("Google", "Chromium", "Google Chromium"), ("Plex", "Media Server", "Plex Media Server"),
                                       ("Barracuda Networks", "Barracuda Email Security Gateway", "Barracuda Email Security Gateway"),
                                       ("", "Kernel", "Kernel")):
            self.assertEqual(render.product_name({"vendor": vendor, "product": product}), shown)
        self.assertIn("Vulnerabilidades", (self.out / "index.html").read_text(encoding="utf-8"))

    def test_home_shows_the_radar_in_numbers(self):
        home = (self.out / "index.html").read_text(encoding="utf-8")
        self.assertIn('<figure class="map">', home)
        self.assertIn('class="land"', home)
        self.assertIn('<ol class="bars">', home)
        self.assertIn("De dónde viene la información", home)
        self.assertIn("Where the information comes from", (self.out / "en.html").read_text(encoding="utf-8"))

    def test_pages_carry_no_inline_styles(self):
        # La política de seguridad solo admite la hoja de estilos propia.
        for path in self.pages():
            self.assertIsNone(re.search(r'\sstyle="', path.read_text(encoding="utf-8")), path.name)

    def test_country_terms_match_whole_words(self):
        self.assertTrue(render.COUNTRY_PATTERNS["us"].search("ataque en estados unidos"))
        self.assertFalse(render.COUNTRY_PATTERNS["in"].search("indiana jones"))
        self.assertFalse(render.COUNTRY_PATTERNS["cu"].search("cubadebate"))

    def test_brand_assets_exist(self):
        for name in ("favicon.ico", "og.png", "icons/rr-icon.svg", "icons/rr-apple-touch-icon.png", "icons/rr-maskable-512.png"):
            self.assertTrue((self.out / name).is_file(), name)
        manifest = json.loads((self.out / "manifest.webmanifest").read_text(encoding="utf-8"))
        for icon in manifest["icons"]:
            self.assertTrue((self.out / icon["src"].lstrip("/")).is_file(), icon["src"])
        self.assertIn("maskable", {i["purpose"] for i in manifest["icons"]})

    def test_internal_links_resolve(self):
        missing = set()
        for path in self.pages():
            for href in re.findall(r'href="(/[^"#]*)"', path.read_text(encoding="utf-8")):
                target = self.out / href.lstrip("/")
                if href == "/" or target.is_file() or target.with_suffix(target.suffix + ".html").is_file() \
                        or (self.out / (href.lstrip("/") + ".html")).is_file():
                    continue
                missing.add(href)
        self.assertEqual(missing, set())

    def test_security_txt(self):
        text = (self.out / ".well-known/security.txt").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^Contact: mailto:\S+@\S+$")
        self.assertRegex(text, r"(?m)^Expires: \d{4}-")


if __name__ == "__main__":
    unittest.main()
