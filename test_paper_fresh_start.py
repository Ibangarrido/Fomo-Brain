"""Offline safety checks for independent PAPER fresh-start cohorts."""
import json
import os
import tempfile
import unittest
from paper_fresh_start import initialize, resume_or_initialize, WALLETS

class FreshStartTests(unittest.TestCase):
    def test_two_independent_wallets_and_no_legacy_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            legacy = os.path.join(d, "fomo_lab_m4_fresh_r1.json")
            with open(legacy, "w") as f: f.write('{"cash":95.55,"positions":[{"symbol":"MACCA"}]}')
            for name in WALLETS:
                path = initialize(name, d, now=__import__("datetime").datetime(2026,10,28,tzinfo=__import__("datetime").timezone.utc))
                with open(path) as f: state = json.load(f)
                self.assertEqual(state["cash"], 100)
                self.assertEqual(state["positions"], [])
                self.assertEqual(state["closed"], [])
                self.assertFalse(state["fresh_start"]["real_trading"])
                with self.assertRaises(FileExistsError): initialize(name, d)
            with open(legacy) as f: self.assertEqual(f.read(), '{"cash":95.55,"positions":[{"symbol":"MACCA"}]}')
    def test_cohort_resumes_without_resetting_balances_or_positions(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(resume_or_initialize(d), "INITIALIZED")
            m4 = os.path.join(d, WALLETS["m4_fresh"])
            with open(m4) as f: state = json.load(f)
            state["cash"] = 93.0
            state["positions"] = [{"address": "paper-only"}]
            with open(m4, "w") as f: json.dump(state, f)
            self.assertEqual(resume_or_initialize(d), "RESUMED")
            with open(m4) as f: self.assertEqual(json.load(f), state)

    def test_partial_or_invalid_restore_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            initialize("m4_fresh", d)
            with self.assertRaisesRegex(ValueError, "Incomplete"):
                resume_or_initialize(d)
            self.assertFalse(os.path.exists(os.path.join(d, WALLETS["continuation_control"])))
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(resume_or_initialize(d), "INITIALIZED")
            path = os.path.join(d, WALLETS["m4_fresh"])
            with open(path, "w") as f: f.write('{"broken":true}')
            with self.assertRaisesRegex(ValueError, "Invalid"):
                resume_or_initialize(d)
            with open(path) as f: self.assertEqual(f.read(), '{"broken":true}')

    def test_unknown_wallet_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError): initialize("main", d)
            self.assertEqual(os.listdir(d), [])

if __name__ == "__main__": unittest.main()
