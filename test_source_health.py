"""Offline source health tests; no network or trading."""
import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from source_health import assess, audit

NOW = datetime(2026, 10, 26, 9, 0, tzinfo=timezone.utc)

class SourceHealthTests(unittest.TestCase):
    def test_gecko_outage_is_not_success(self):
        self.assertEqual(assess("geckoterminal", {"status": "UNAVAILABLE:HTTPError", "at": NOW.isoformat(), "candidates": []}, NOW)["state"], "UNAVAILABLE")

    def test_gecko_zero_candidates_is_not_an_outage(self):
        self.assertEqual(assess("geckoterminal", {"status": "OK", "at": NOW.isoformat(), "candidates": []}, NOW)["state"], "HEALTHY")

    def test_gmgn_missing_key(self):
        self.assertEqual(assess("gmgn", {"status": "MISSING_API_KEY"}, NOW)["state"], "AUTH_REQUIRED")

    def test_gmgn_schema_only(self):
        self.assertEqual(assess("gmgn", {"status": "AWAITING_SCHEMA_VALIDATION"}, NOW)["state"], "UNVALIDATED")

    def test_v13_partial_errors(self):
        self.assertEqual(assess("v13", {"paper_only": True, "errors": [{"source": "a"}], "at": NOW.isoformat()}, NOW)["state"], "DEGRADED")

    def test_v13_paper_only_guard(self):
        self.assertEqual(assess("v13", {"paper_only": False, "errors": [], "at": NOW.isoformat()}, NOW)["state"], "INVALID")

    def test_cooker_stale(self):
        self.assertEqual(assess("cooker", {"status": "SYNCED", "checked_at": (NOW - timedelta(minutes=80)).isoformat()}, NOW)["state"], "STALE")

    def test_cooker_history_gap(self):
        self.assertEqual(assess("cooker", {"status": "HISTORY_GAP_CURSOR_RETAINED"}, NOW)["state"], "DEGRADED")

    def test_missing_report(self):
        with tempfile.TemporaryDirectory() as d:
            result = audit({"geckoterminal": Path(d) / "absent.json"}, now=NOW)
            self.assertEqual(result["sources"]["geckoterminal"]["state"], "NOT_OBSERVED")
            self.assertEqual(result["observed_count"], 0)

    def test_valid_report_from_disk(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "report.json"
            path.write_text(json.dumps({"status": "OK", "at": NOW.isoformat(), "candidates": []}))
            self.assertEqual(audit({"geckoterminal": path}, now=NOW)["healthy_count"], 1)

if __name__ == "__main__":
    unittest.main()
