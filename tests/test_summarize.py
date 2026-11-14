import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "collector"))

import summarize  # noqa: E402

NOW = dt.datetime(2026, 11, 14, 12, tzinfo=dt.timezone.utc)
LONG = " ".join(["La empresa confirmó el ataque y pidió actualizar a la versión 2.4.1 de inmediato."] * 30)
PAGE = f"<html><body><article><p>{LONG}</p><p>{LONG}</p></article></body></html>".encode()


def item(n, **extra):
    return {"id": f"id{n}", "title": f"Nota {n}", "url": f"https://medio.test/{n}", "source": "Medio",
            "summary": "Resumen corto.", "region": "mundo", "category": "General", "alert": False,
            "published": f"2026-11-13T{10 + n:02d}:00:00+00:00", "first_seen": "2026-11-13T10:00:00+00:00", **extra}


def answer(paragraphs=4):
    body = [f"Párrafo propio número {n} con los datos de la nota." for n in range(paragraphs)]
    return json.dumps({"es": {"title": "Titular", "summary": "Bajada.", "body": body},
                       "en": {"title": "Headline", "summary": "Dek.", "body": body}})


class SummarizeTests(unittest.TestCase):
    def run_summarize(self, items, ask, **kwargs):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        data = Path(temp.name)
        (data / "2026-11.json").write_text(json.dumps(items), encoding="utf-8")
        (data / "latest.json").write_text(json.dumps({"items": items}), encoding="utf-8")
        report = summarize.summarize({"feeds": []}, data, NOW, ask=ask, fetch=lambda url: PAGE, **kwargs)
        month = {i["id"]: i for i in json.loads((data / "2026-11.json").read_text(encoding="utf-8"))}
        latest = {i["id"]: i for i in json.loads((data / "latest.json").read_text(encoding="utf-8"))["items"]}
        return report, month, latest

    def test_writes_both_languages_and_never_stores_the_original(self):
        prompts = []

        def ask(messages):
            prompts.append(messages)
            return answer()
        report, month, latest = self.run_summarize([item(1)], ask)
        self.assertEqual(report["written"], 1)
        self.assertEqual(month["id1"]["tr"]["es"]["title"], "Titular")
        self.assertEqual(len(latest["id1"]["tr"]["en"]["body"]), 4)
        self.assertIn("propias palabras", prompts[0][0]["content"])
        self.assertIn("versión 2.4.1", prompts[0][1]["content"])
        self.assertNotIn("2.4.1", json.dumps(month))

    def test_licensed_sources_are_translated_in_full(self):
        prompts = []

        def ask(messages):
            prompts.append(messages)
            return answer(6)
        body = [["h", "Resumen"], ["p", LONG]]
        self.run_summarize([item(1, body=body, reuse="Dominio público.")], ask)
        self.assertIn("Traducilo completo", prompts[0][0]["content"])

    def test_bad_answers_are_retried_then_given_up(self):
        items = [item(1)]
        report, month, _ = self.run_summarize(items, lambda m: "no es json")
        self.assertEqual(report["failed"], 1)
        self.assertEqual(month["id1"]["tr_tries"], 1)
        self.assertNotIn("tr", month["id1"])
        report, _, _ = self.run_summarize([dict(month["id1"], tr_tries=summarize.MAX_TRIES)], lambda m: answer())
        self.assertEqual(report["written"], 0)

    def test_too_short_answer_for_a_long_article_is_rejected(self):
        report, month, _ = self.run_summarize([item(1)], lambda m: answer(1))
        self.assertEqual(report["failed"], 1)

    def test_alerts_first_then_newest_and_stops_at_the_deadline(self):
        order = []

        def ask(messages):
            order.append(messages[1]["content"].split("Titular: ")[1].split("\n")[0])
            return answer()
        ticks = iter([0, 0, 0, 10_000])
        items = [item(1), item(2), item(3, alert=True)]
        report, _, _ = self.run_summarize(items, ask, minutes=1, clock=lambda: next(ticks))
        self.assertEqual(order, ["Nota 3", "Nota 2"])
        self.assertEqual(report["left"], 1)

    def test_skips_aggregators_done_and_old_notes(self):
        called = []
        items = [item(1, url="https://news.google.com/rss/articles/x"), item(2, tr={"es": {}}),
                 item(3, published="2026-08-01T00:00:00+00:00")]
        report, _, _ = self.run_summarize(items, lambda m: called.append(1) or answer())
        self.assertEqual(called, [])
        self.assertEqual(report["written"], 0)

    def test_code_fences_are_tolerated(self):
        self.assertEqual(summarize.parse("```json\n" + answer() + "\n```", 3)["en"]["title"], "Headline")


if __name__ == "__main__":
    unittest.main()
