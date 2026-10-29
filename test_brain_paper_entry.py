"""Offline regression tests for the guarded PAPER entry point."""
import os
import unittest
from unittest.mock import patch

import brain_paper_entry


class PaperEntryTests(unittest.TestCase):
    def test_missing_legacy_pin_fails_closed(self):
        with patch.dict(os.environ, {
            "BRAIN_CONTROL_LEGACY_ADDRESS": "",
            "BRAIN_PATTERN_LEGACY_ADDRESS": "",
        }), patch("brain_paper_entry.subprocess.call") as call:
            self.assertEqual(brain_paper_entry.main(), 2)
            call.assert_not_called()

    def test_entry_preserves_quote_guard_and_isolation(self):
        with patch.dict(os.environ, {
            "BRAIN_CONTROL_LEGACY_ADDRESS": "legacy-control",
            "BRAIN_PATTERN_LEGACY_ADDRESS": "legacy-pattern",
            "BRAIN_QUOTE_GUARD": "0",
        }), patch("brain_paper_entry.subprocess.call", return_value=0) as call:
            self.assertEqual(brain_paper_entry.main(), 0)
            args, kwargs = call.call_args
            self.assertEqual(args[0][1], "fomo_brain.py")
            self.assertEqual(kwargs["env"]["BRAIN_QUOTE_GUARD"], "1")
            self.assertEqual(kwargs["env"]["BRAIN_UNKNOWN_ISOLATION"], "1")
            self.assertEqual(kwargs["env"]["BRAIN_M4_LAB"], "0")

    def test_engine_failure_is_propagated(self):
        with patch.dict(os.environ, {
            "BRAIN_CONTROL_LEGACY_ADDRESS": "legacy-control",
            "BRAIN_PATTERN_LEGACY_ADDRESS": "legacy-pattern",
        }), patch("brain_paper_entry.subprocess.call", return_value=9):
            self.assertEqual(brain_paper_entry.main(), 9)


if __name__ == "__main__":
    unittest.main()
