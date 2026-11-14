import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "collector"))

import enrich  # noqa: E402

NOW = dt.datetime(2026, 11, 14, 12, tzinfo=dt.timezone.utc)
PAGE = b"""<html><head><meta property="og:image" content="/fotos/espia.jpg">
<script>var x = "<p>no es texto</p>";</script></head><body>
<nav><p>Inicio Noticias Contacto y muchos otros enlaces del menu principal</p></nav>
<article><h2>Lo que paso</h2><p>Primer parrafo de la nota con suficiente texto para contar como cuerpo real.</p>
<ul><li>Un punto</li></ul><p>Please share your thoughts on our product survey, it takes a minute.</p>
<p>Segundo parrafo de la nota, tambien con suficiente texto para no ser descartado.</p></article>
<footer><p>Todos los derechos reservados, pie de pagina del sitio con texto largo.</p></footer></body></html>"""


def item(n, **extra):
    return {"id": f"id{n}", "title": f"Nota {n}", "url": f"https://medio.test/{n}", "source": "Medio",
            "summary": "", "region": "mundo", "category": "General", "alert": False,
            "published": "2026-11-13T10:00:00+00:00", "first_seen": "2026-11-13T10:00:00+00:00", **extra}


class ArticleTests(unittest.TestCase):
    def test_reads_image_and_body_but_not_menus_scripts_or_boilerplate(self):
        image, blocks = enrich.read_article(PAGE, "https://medio.test/nota")
        self.assertEqual(image, "https://medio.test/fotos/espia.jpg")
        self.assertEqual([k for k, _ in blocks], ["h", "p", "li", "p"])
        text = " ".join(t for _, t in blocks)
        self.assertNotIn("menu", text)
        self.assertNotIn("no es texto", text)
        self.assertNotIn("survey", text)
        self.assertNotIn("derechos", text)

    def test_generic_images_are_detected(self):
        self.assertTrue(enrich.is_generic("https://a.test/wp-content/uploads/2023/10/cybersecurity-news.jpg"))
        self.assertTrue(enrich.is_generic("https://a.test/images/preview_image.png"))
        self.assertFalse(enrich.is_generic("https://a.test/uploads/2026/11/FAA_Cyberattack.jpg"))

    def test_insecure_image_is_upgraded_or_dropped(self):
        image, _ = enrich.read_article(b'<meta property="og:image" content="http://a.test/x.jpg">', "https://a.test/")
        self.assertEqual(image, "https://a.test/x.jpg")
        image, _ = enrich.read_article(b'<meta property="og:image" content="javascript:alert(1)">', "https://a.test/")
        self.assertEqual(image, "")


class EnrichTests(unittest.TestCase):
    def run_enrich(self, items, config_extra=None, pages=None):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        data = Path(temp.name)
        (data / "2026-11.json").write_text(json.dumps(items), encoding="utf-8")
        (data / "latest.json").write_text(json.dumps({"items": items, "months": ["2026-11"]}), encoding="utf-8")
        config = {"feeds": [{"name": "Medio"}, {"name": "Oficial", "reuse": "Dominio público."}], **(config_extra or {})}
        fetched = []

        def fetch(url):
            fetched.append(url)
            return (pages or {}).get(url, PAGE)
        report = enrich.enrich(config, data, NOW, fetch=fetch)
        month = json.loads((data / "2026-11.json").read_text(encoding="utf-8"))
        latest = json.loads((data / "latest.json").read_text(encoding="utf-8"))
        return report, {i["id"]: i for i in month}, latest, fetched

    def test_full_text_only_for_licensed_sources(self):
        _, items, latest, _ = self.run_enrich([item(1), item(2, source="Oficial", url="https://gob.test/2")])
        self.assertNotIn("body", items["id1"])
        self.assertEqual(items["id1"]["image"], "https://medio.test/fotos/espia.jpg")
        self.assertEqual(items["id2"]["body"][0], ["h", "Lo que paso"])
        self.assertEqual(items["id2"]["reuse"], "Dominio público.")
        self.assertIn("body", {i["id"]: i for i in latest["items"]}["id2"])

    def test_skips_aggregators_old_and_done_items(self):
        items = [item(1, url="https://news.google.com/rss/articles/abc"), item(2, published="2026-08-01T00:00:00+00:00"),
                 item(3, enriched="2026-11-13T00:00:00+00:00"), item(4)]
        report, _, _, fetched = self.run_enrich(items)
        self.assertEqual(fetched, ["https://medio.test/4"])
        self.assertEqual(report["read"], 1)

    def test_shared_image_is_the_outlets_default(self):
        page = b'<meta property="og:image" content="https://medio.test/portada.jpg">'
        _, items, _, _ = self.run_enrich([item(1), item(2)], pages={"https://medio.test/1": page, "https://medio.test/2": page})
        self.assertNotIn("image", items["id1"])
        self.assertNotIn("image", items["id2"])

    def test_a_failing_page_does_not_stop_the_rest(self):
        def boom(url):
            raise OSError("caida")
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        data = Path(temp.name)
        (data / "2026-11.json").write_text(json.dumps([item(1)]), encoding="utf-8")
        report = enrich.enrich({"feeds": []}, data, NOW, fetch=boom)
        self.assertEqual(report["failed"], 1)
        self.assertIn("enriched", json.loads((data / "2026-11.json").read_text(encoding="utf-8"))[0])

    def test_removed_notes_and_sources_disappear(self):
        removed = {"removed": {"ids": ["id1"], "urls": ["https://medio.test/2/"], "sources": ["Otro"], "domains": ["borrado.test"]}}
        items = [item(1), item(2), item(3, source="Otro"), item(4, url="https://www.sub.borrado.test/4"), item(5)]
        report, kept, latest, _ = self.run_enrich(items, removed)
        self.assertEqual(sorted(kept), ["id5"])
        self.assertEqual([i["id"] for i in latest["items"]], ["id5"])
        self.assertEqual(report["purged"], 4)


if __name__ == "__main__":
    unittest.main()
