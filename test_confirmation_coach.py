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


class ConfirmationCoachContractTests(unittest.TestCase):
    def test_both_windows_and_exact_remaining_boundary(self):
        for window in (90, 120):
            for remaining, expected in ((29, 0), (30, 1), (31, 1)):
                from datetime import timedelta
                row = event(at=(NOW-timedelta(seconds=window-remaining)).isoformat(),
                            confirmation_window_seconds=window)
                self.assertEqual(diagnose([row], NOW)["pending_recheck_candidates"], expected)

    def test_drift_labels_numeric_threshold_and_all_reasons(self):
        for reason in ("PRICE_DRIFT_GT_5PCT", "PRICE_DRIFT_UNKNOWN"):
            report = diagnose([event(reasons=[reason, "REFERENCE_EXPIRED_OR_INVALID"])], NOW)
            self.assertEqual(report["blockers"]["quote_drift"], 1)
            self.assertEqual(report["blockers"]["reference_expired"], 1)
        for value, expected in ((5, False), (-5, False), (5.01, True), (-5.01, True)):
            report = diagnose([event(status="REFERENCE_AVAILABLE", reasons=[], price_drift_pct=value)], NOW)
            self.assertEqual("quote_drift" in report["blockers"], expected)

    def test_out_of_order_and_latest_invalid_block_old_candidate(self):
        older = event(at="2026-10-29T17:59:50+00:00")
        for newer in (event(status="REFERENCE_AVAILABLE", reasons=[]),
                      event(status="INVALID_FRESH_RECEIPT", reasons=[])):
            for rows in ([older, newer], [newer, older]):
                self.assertEqual(diagnose(rows, NOW)["pending_recheck_candidates"], 0)

    def test_missing_pairs_and_bad_numeric_ages_never_recheck(self):
        for fields in ({"reference_pair": None, "current_pair": None},
                       {"fresh_receipt_age_seconds": True},
                       {"fresh_receipt_age_seconds": float("nan")},
                       {"fresh_receipt_age_seconds": -1},
                       {"confirmation_window_seconds": 100},
                       {"reasons": None, "status": "INVALID_FRESH_RECEIPT"}):
            self.assertEqual(diagnose([event(**fields)], NOW)["pending_recheck_candidates"], 0)

    def test_missing_schema_empty_and_corrupt_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for name, content in (("clean.json", '{"decisions": [{"reason":"low_liquidity"}]}'),
                                  ("empty.json", '{"confirmation_audit": []}'),
                                  ("bad.json", '{')):
                path = Path(tmp)/name
                path.write_text(content)
                paths.append(str(path))
            reports = report_paper_files(paths, NOW)["reports"]
            self.assertEqual(reports["clean.json"]["status"], "unsupported_schema")
            self.assertEqual(reports["clean.json"]["strategic_decisions"][0]["reason"], "low_liquidity")
            self.assertEqual(reports["empty.json"]["status"], "no_events")
            self.assertEqual(reports["bad.json"]["status"], "unreadable")

    def test_cli_replay_preserves_bytes_and_rejects_input_output_alias(self):
        import subprocess
        import sys
        script = str(Path(__file__).with_name("confirmation_coach.py").resolve())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"paper.json"
            path.write_text(json.dumps({"cash":90, "reserve":1, "positions":{},
                                        "confirmation_audit":[event()]}))
            original = path.read_bytes()
            command = [sys.executable, script, str(path), "--now", NOW.isoformat()]
            for _ in range(2):
                result = subprocess.run(command, cwd=tmp, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads((Path(tmp)/"confirmation_coach_report.json").read_text())
                self.assertEqual(report["reports"]["paper.json"]["pending_recheck_candidates"], 1)
                self.assertEqual(path.read_bytes(), original)
            result = subprocess.run(command+["--output", str(path)], cwd=tmp, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
