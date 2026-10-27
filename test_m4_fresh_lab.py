"""Offline regression for the independent M4 fresh PAPER wrapper."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch
import m4_fresh_lab as fresh

class FreshM4Tests(unittest.TestCase):
    def test_disabled_does_not_simulate(self):
        with patch.dict(os.environ, BRAIN_M4_FRESH_LAB="0"):
            fresh.run([], lambda *a, **k: self.fail("should be disabled"))

    def test_separate_file_and_no_legacy_transfer(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, fresh.FILE)
            def fake_simulate(ranking, filename, label, **kwargs):
                self.assertEqual(filename, fresh.FILE)
                self.assertEqual(kwargs, {"confirm": True, "entry_mode": "early", "min_buy_ratio": .60})
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({"cash": 100., "reserve": 0., "positions": [], "closed": []}, f)
            old = os.getcwd()
            try:
                os.chdir(d)
                with patch.dict(os.environ, BRAIN_M4_FRESH_LAB="1"):
                    fresh.run([], fake_simulate)
            finally:
                os.chdir(old)
            self.assertTrue(os.path.isfile(path))

if __name__ == "__main__":
    unittest.main()
