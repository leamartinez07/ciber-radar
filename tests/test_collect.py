import datetime as dt
import json
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "collector"))

import collect  # noqa: E402

NOW = dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.timezone.utc)
CONFIG = tomllib.loads((ROOT / "feeds.toml").read_text(encoding="utf-8"))


def rss(*items: tuple[str, str, str]) -> bytes:
    body = "".join(
        f"<item><title>{t}</title><link>{u}</link><pubDate>{d}</pubDate>"
        f"<description>&lt;p&gt;Texto &lt;b&gt;limpio&lt;/b&gt;&lt;/p&gt;</description></item>"
        for t, u, d in items
    )
    return f'<?xml version="1.0"?><rss><channel>{body}</channel></rss>'.encode()


RECENT = "Tue, 10 Nov 2026 10:00:00 +0000"
AR_INCIDENT = "Ciberataque contra un hospital de Argentina deja sin sistema a miles"


def config_with(feeds=None, **limits):
    config = dict(CONFIG)
    config["feeds"] = feeds or [{"name": "Prueba", "url": "https://a.test/f", "region": "mundo"}]
    config["limits"] = {**CONFIG["limits"], **limits}
    return config


class ParsingTests(unittest.TestCase):
    def test_atom(self):
        data = (
            b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Hola</title>'
            b'<link rel="replies" href="https://a.test/c"/><link rel="alternate" href="https://a.test/1"/>'
            b"<published>2026-11-09T10:00:00-03:00</published><summary>S</summary></entry></feed>"
        )
        entry = collect.parse_feed(data)[0]
        self.assertEqual(entry["link"], "https://a.test/1")
        self.assertEqual(entry["date"], "2026-11-09T10:00:00-03:00")

    def test_rejects_entity_expansion(self):
        data = b'<!DOCTYPE x [<!ENTITY a "aaaa">]><rss><channel><item><title>&a;</title></item></channel></rss>'
        with self.assertRaises(ValueError):
            collect.parse_feed(data)

    def test_two_digit_year_date(self):
        self.assertEqual(collect.parse_date("Mon, 09 Nov 26 12:00:00 +0000", NOW).year, 2026)

    def test_future_date_is_clamped(self):
        self.assertEqual(collect.parse_date("Mon, 09 Nov 2099 12:00:00 +0000", NOW), NOW)

    def test_only_http_links(self):
        self.assertEqual(collect.safe_url("javascript:alert(1)"), "")
        self.assertEqual(collect.safe_url("data:text/html,x"), "")
        self.assertEqual(collect.safe_url("https://a.test/x"), "https://a.test/x")

    def test_canonical_drops_tracking(self):
        self.assertEqual(
            collect.canonical_url("http://A.test/n/?utm_source=x&id=1#top"),
            "https://a.test/n?id=1",
        )


class ItemTests(unittest.TestCase):
    rules = collect.Rules(CONFIG)

    def item(self, title, feed=None, **extra):
        entry = {"title": title, "link": "https://a.test/1", "date": RECENT, "summary": "", "source": "", **extra}
        return collect.build_item(feed or {"name": "F", "region": "mundo"}, entry, NOW, self.rules)

    def test_html_is_stripped(self):
        item = self.item("&lt;img src=x onerror=alert(1)&gt;Título real de la nota")
        self.assertEqual(item["title"], "Título real de la nota")

    def test_argentine_incident_alerts(self):
        item = self.item(AR_INCIDENT)
        self.assertTrue(item["alert"])
        self.assertEqual(item["region"], "ar")

    def test_accents_do_not_matter(self):
        self.assertTrue(self.item("Filtración de datos en el ANSES afecta a jubilados")["alert"])

    def test_argentina_without_incident_is_quiet(self):
        self.assertFalse(self.item("Argentina presenta su nuevo plan de conectividad rural")["alert"])

    def test_global_critical_alerts(self):
        self.assertTrue(self.item("Microsoft patches zero-day exploited by attackers")["alert"])

    def test_word_boundaries(self):
        self.assertIsNone(self.item("Caballos de carrera ganan en la caballeriza", {"name": "F", "region": "mundo", "require_cyber": True}))

    def test_google_suffix_removed_and_source_used(self):
        feed = {"name": "G", "region": "ar", "aggregator": True}
        item = self.item("Nueva estafa digital en bancos - Infobae", feed, source="Infobae", source_url="https://www.infobae.com")
        self.assertEqual(item["title"], "Nueva estafa digital en bancos")
        self.assertEqual(item["source"], "Infobae")

    def test_aggregator_keeps_only_trusted_outlets(self):
        feed = {"name": "G", "region": "ar", "aggregator": True, "require_cyber": True}
        title = "Hackeo a un banco expone datos de clientes"
        self.assertIsNone(self.item(title, feed, source="Sitio X", source_url="https://sitio-desconocido.test"))
        self.assertIsNone(self.item(title, feed, source="Sin URL"))
        self.assertIsNone(self.item(title, feed, source="Falso", source_url="https://clarin.com.falso.test"))
        self.assertIsNotNone(self.item(title, feed, source="Clarín", source_url="https://www.clarin.com"))
        self.assertIsNotNone(self.item(title, feed, source="LN", source_url="https://www.lanacion.com.ar"))

    def test_source_url_is_parsed(self):
        data = (b'<?xml version="1.0"?><rss><channel><item><title>T</title><link>https://n.test/1</link>'
                b'<source url="https://www.infobae.com">Infobae</source></item></channel></rss>')
        self.assertEqual(collect.parse_feed(data)[0]["source_url"], "https://www.infobae.com")

    def test_title_prefix_filter(self):
        feed = {"name": "E", "region": "mundo", "title_prefix": "ciberseguridad | "}
        self.assertIsNone(self.item("otras noticias | Feria de empleo", feed))
        self.assertEqual(self.item("ciberseguridad | Ataque masivo", feed)["title"], "Ataque masivo")


class RunTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.data = Path(temp.name) / "data"
        self.state = Path(temp.name) / "state.json"
        self.sent = []

    def run_with(self, feed_bytes, config=None, now=NOW, notify=None, topic="t"):
        return collect.run(
            config or config_with(), self.data, self.state, now,
            fetch=lambda _: feed_bytes,
            notify=notify or self.sent.append,
            topic=topic,
            site_url="https://sitio.test/",
        )

    def latest(self):
        return json.loads((self.data / "latest.json").read_text(encoding="utf-8"))

    def test_first_run_stores_but_does_not_notify(self):
        report = self.run_with(rss((AR_INCIDENT, "https://a.test/1", RECENT)))
        self.assertEqual(report["new"], 1)
        self.assertEqual(self.sent, [])
        self.assertEqual(len(self.latest()["items"]), 1)

    def test_new_alert_notifies_once(self):
        first = rss(("Nota vieja cualquiera de seguridad", "https://a.test/0", RECENT))
        self.run_with(first)
        second = rss(("Nota vieja cualquiera de seguridad", "https://a.test/0", RECENT), (AR_INCIDENT, "https://a.test/1", RECENT))
        self.run_with(second)
        self.run_with(second)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0]["click"], "https://a.test/1")
        self.assertEqual(self.sent[0]["priority"], 4)

    def test_same_title_in_two_sources_is_one_item(self):
        report = self.run_with(rss((AR_INCIDENT, "https://a.test/1", RECENT), (AR_INCIDENT, "https://b.test/2", RECENT)))
        self.assertEqual(report["new"], 1)

    def test_old_items_are_skipped(self):
        report = self.run_with(rss(("Nota muy antigua de seguridad informática", "https://a.test/1", "Mon, 01 Jan 2024 10:00:00 +0000")))
        self.assertEqual(report["new"], 0)

    def test_overflow_becomes_digest(self):
        self.run_with(rss(("Primera nota sin importancia alguna", "https://a.test/0", RECENT)))
        places = ["hospital rosario", "banco mendoza", "escuela salta", "municipio jujuy", "clinica neuquen",
                  "empresa tucuman", "correo chaco", "puerto bahia", "teatro corrientes"]
        many = [(f"Ciberataque golpea {p} Argentina", f"https://a.test/{i+1}", RECENT) for i, p in enumerate(places)]
        self.run_with(rss(*many))
        self.assertEqual(len(self.sent), 5)
        self.assertIn("5 alertas más", self.sent[-1]["title"])
        self.assertEqual(self.sent[-1]["click"], "https://sitio.test/")

    def test_same_event_from_two_outlets_notifies_once(self):
        self.run_with(rss(("Primera nota sin importancia alguna", "https://a.test/0", RECENT)))
        self.run_with(rss(("Hackeo masivo al sistema de salud de Argentina", "https://a.test/1", RECENT)))
        self.run_with(rss(("Hackeo masivo golpea al sistema de salud de Argentina", "https://b.test/2", RECENT)))
        self.assertEqual(len(self.sent), 1)

    def test_failed_send_is_retried(self):
        self.run_with(rss(("Primera nota sin importancia alguna", "https://a.test/0", RECENT)))

        def broken(_):
            raise OSError("sin red")

        feed = rss((AR_INCIDENT, "https://a.test/1", RECENT))
        self.run_with(feed, notify=broken)
        self.assertEqual(self.sent, [])
        self.run_with(feed)
        self.assertEqual(len(self.sent), 1)
        self.run_with(feed)
        self.assertEqual(len(self.sent), 1)

    def test_daily_budget(self):
        config = config_with(notify_per_day=1)
        self.run_with(rss(("Primera nota sin importancia alguna", "https://a.test/0", RECENT)), config)
        self.run_with(rss((AR_INCIDENT, "https://a.test/1", RECENT)), config)
        self.run_with(rss(("Hackeo masivo a una empresa argentina de salud", "https://a.test/2", RECENT)), config)
        self.assertEqual(len(self.sent), 1)

    def test_one_broken_source_is_tolerated(self):
        feeds = [
            {"name": "Buena", "url": "https://a.test/ok", "region": "mundo"},
            {"name": "Mala", "url": "https://a.test/bad", "region": "mundo"},
        ]

        def fetch(url):
            if url.endswith("bad"):
                raise OSError("caída")
            return rss(("Una nota real sobre seguridad", "https://a.test/1", RECENT))

        report = collect.run(config_with(feeds), self.data, self.state, NOW, fetch=fetch)
        self.assertEqual(report["failed"], ["Mala"])

    def test_mass_failure_leaves_data_untouched(self):
        def fetch(_):
            raise OSError("caída")

        with self.assertRaises(RuntimeError):
            collect.run(config_with(), self.data, self.state, NOW, fetch=fetch)
        self.assertFalse(self.state.exists())
        self.assertFalse((self.data / "latest.json").exists())

    def test_topic_never_reaches_public_files(self):
        self.run_with(rss((AR_INCIDENT, "https://a.test/1", RECENT)), topic="tema-secreto-xyz")
        self.run_with(rss(("Hackeo masivo a una empresa argentina", "https://a.test/2", RECENT)), topic="tema-secreto-xyz")
        for path in [*self.data.iterdir(), self.state]:
            self.assertNotIn("tema-secreto-xyz", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
