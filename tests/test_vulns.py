import datetime as dt
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "collector"))

import vulns  # noqa: E402

vulns.RETRY_SECONDS = 0

NOW = dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.timezone.utc)
KEV = {"vulnerabilities": [
    {"cveID": "CVE-2026-1111", "vendorProject": "Acme", "product": "Router", "vulnerabilityName": "Acme Router RCE",
     "shortDescription": "<b>Remote</b> code execution.", "dateAdded": "2026-11-09", "dueDate": "2026-11-30",
     "knownRansomwareCampaignUse": "Known"},
    {"cveID": "CVE-2020-0001", "dateAdded": "2020-01-01"},
    {"cveID": "<script>", "dateAdded": "2026-11-09"},
    {"cveID": "CVE-2026-2222", "dateAdded": "2026-11-09'><img>"},
]}
NVD = {"vulnerabilities": [
    {"cve": {"id": "CVE-2026-3333", "published": "2026-11-10T01:00:00.000", "vulnStatus": "Received",
             "descriptions": [{"lang": "en", "value": "Critical bug."}],
             "metrics": {"cvssMetricV31": [{"cvssData": {"baseScore": 9.8}}]}}},
    {"cve": {"id": "CVE-2026-4444", "published": "2026-11-10T01:00:00.000",
             "metrics": {"cvssMetricV31": [{"cvssData": {"baseScore": 7.5}}]}}},
    {"cve": {"id": "CVE-2026-5555", "published": "2026-11-10T01:00:00.000", "vulnStatus": "Rejected",
             "metrics": {"cvssMetricV40": [{"cvssData": {"baseScore": 10}}]}}},
]}
EPSS = {"data": [{"cve": "CVE-2026-1111", "epss": "0.91", "percentile": "0.99"},
                 {"cve": "CVE-2026-3333", "epss": "nan?", "percentile": "x"}]}


def fake(kev=KEV, nvd=NVD, epss=EPSS, broken=()):
    calls = []

    def fetch(url):
        calls.append(url)
        for name, payload in (("cisa.gov", kev), ("nvd.nist.gov", nvd), ("first.org", epss)):
            if name in url:
                if name in broken:
                    raise OSError("caída")
                return json.dumps(payload).encode()
        raise AssertionError(url)
    fetch.calls = calls
    return fetch


class VulnTests(unittest.TestCase):
    def test_kev_is_recent_and_validated(self):
        data = vulns.build(NOW, {}, fake())
        self.assertEqual([e["cve"] for e in data["kev"]], ["CVE-2026-1111"])
        entry = data["kev"][0]
        self.assertEqual(entry["description"], "Remote code execution.")
        self.assertTrue(entry["ransomware"])
        self.assertEqual(entry["url"], "https://nvd.nist.gov/vuln/detail/CVE-2026-1111")
        self.assertEqual(entry["epss"], 0.91)
        self.assertEqual(data["kev_total"], 4)

    def test_nvd_keeps_only_critical_and_not_rejected(self):
        data = vulns.build(NOW, {}, fake())
        self.assertEqual([e["cve"] for e in data["critical"]], ["CVE-2026-3333"])
        self.assertEqual(data["critical"][0]["score"], 9.8)
        self.assertIsNone(data["critical"][0]["epss"])

    def test_failed_source_keeps_previous_data(self):
        first = vulns.build(NOW, {}, fake())
        second = vulns.build(NOW, first, fake(broken=("cisa.gov",)))
        self.assertEqual(second["kev"][0]["cve"], "CVE-2026-1111")
        self.assertFalse(next(s for s in second["sources"] if s["name"] == "CISA KEV")["ok"])

    def test_epss_commas_are_not_encoded(self):
        fetch = fake()
        vulns.build(NOW, {}, fetch)
        epss = [u for u in fetch.calls if "first.org" in u]
        self.assertTrue(epss)
        self.assertIn("CVE-2026-1111,CVE-2026-3333", epss[0])

    def test_new_kev_alerts_only_after_first_run(self):
        current = vulns.build(NOW, {}, fake())
        self.assertEqual(vulns.new_kev({}, current), [])
        previous = {"kev": [{"cve": "CVE-2025-0001"}]}
        self.assertEqual([e["cve"] for e in vulns.new_kev(previous, current)], ["CVE-2026-1111"])
        alert = vulns.kev_alert(current["kev"][0])
        self.assertIn("CVE-2026-1111", alert["title"])
        self.assertIn("ransomware", alert["message"])


if __name__ == "__main__":
    unittest.main()
