import copy
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from confirmation_coach import diagnose, report_paper_files

NOW = datetime(2026, 10, 29, 18, 0, tzinfo=timezone.utc)


def event(address="HI", at="2026-10-29T17:59:55+00:00", **updates):
    value = {
        "at": at, "chain": "solana", "address": address,
        "reference_pair": "pair1", "current_pair": "pair1",
        "status": "RENEWED", "reasons": ["REFERENCE_EXPIRED_OR_INVALID"],
        "fresh_receipt_age_seconds": 0, "confirmation_window_seconds": 90,
    }
    value.update(updates)
    return value


class ConfirmationCoachTests(unittest.TestCase):
    def test_expired_reference_gets_recheck_hint_but_never_entry(self):
        rows = [event()]
        old = copy.deepcopy(rows)
        report = diagnose(rows, NOW)
        self.assertEqual(rows, old)
        self.assertEqual(report["blockers"]["reference_expired"], 1)
        self.assertEqual(report["pending_recheck_candidates"], 1)
        self.assertEqual(report["pending_examples"][0]["suggested_recheck_after_seconds"], 30)
        self.assertFalse(report["entry_authorized"])
        self.assertFalse(report["automatic_fetches"])

    def test_no_recheck_for_stale_invalid_or_wrong_pair(self):
        rows = [
            event("stale", at="2026-10-29T17:57:00+00:00"),
            event("bad", fresh_receipt_age_seconds=45),
            event("changed", current_pair="pair2", reasons=["IDENTITY_CHANGED"]),
            event("invalid", status="INVALID_FRESH_RECEIPT", reasons=["FRESH_RECEIPT_INVALID"]),
        ]
        report = diagnose(rows, NOW)
        self.assertEqual(report["pending_recheck_candidates"], 0)
        self.assertEqual(report["blockers"]["pair_changed"], 1)
        self.assertEqual(report["blockers"]["invalid_receipt"], 1)

    def test_latest_event_overrides_older_recheck_and_future_event_excluded(self):
        rows = [event(), event(status="REFERENCE_AVAILABLE", reasons=[]),
                event("future", at="2026-10-30T18:00:00+00:00")]
        report = diagnose(rows, NOW)
        self.assertEqual(report["pending_recheck_candidates"], 0)
        self.assertEqual(report["blockers"]["invalid_event_time"], 1)
        self.assertEqual(report["blockers"]["reference_available_not_entry"], 1)

    def test_file_report_preserves_original_wallet_and_marks_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            filename = Path(folder) / "paper.json"
            state = {"cash": 89.83, "reserve": 0.55,
                     "positions": [{"address": "MACCA", "price": None}],
                     "confirmation_audit": [event()]}
            filename.write_text(json.dumps(state))
            original = filename.read_bytes()
            report = report_paper_files([str(filename), str(Path(folder) / "missing.json")], NOW)
            self.assertEqual(filename.read_bytes(), original)
            self.assertEqual(report["reports"]["paper.json"]["pending_recheck_candidates"], 1)
            self.assertEqual(report["reports"]["missing.json"]["status"], "missing_file")
            self.assertFalse(report["wallet_state_modified"])

    def test_150_event_cap_and_invalid_timestamps(self):
        rows = [event(str(i)) for i in range(160)]
        rows.append(event("badtime", at="not-a-date"))
        report = diagnose(rows, NOW)
        self.assertEqual(report["events_considered"], 150)
        self.assertEqual(report["blockers"]["invalid_event_time"], 1)
        self.assertLessEqual(len(report["pending_examples"]), 8)


if __name__ == "__main__":
    unittest.main()
