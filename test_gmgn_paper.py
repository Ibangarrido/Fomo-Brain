import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
import gmgn_paper as paper


class GMGNPaperTests(unittest.TestCase):
    def test_initializes_once_and_missing_data_never_fills_or_resets(self):
        seed = Path(paper.SEED).read_text()
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            wallet = os.path.join(directory, 'wallet.json')
            start = os.path.join(directory, 'seed.json')
            preflight = os.path.join(directory, 'source.json')
            Path(start).write_text(seed)
            first = paper.update(wallet, start, preflight)
            self.assertEqual(first['cash_eur'], 100)
            self.assertEqual(first['positions'], [])
            self.assertEqual(first['source_status'], 'NO_PREFLIGHT')
            first['cash_eur'] = 95
            first['closed'] = [{'test_marker': 'preserve history'}]
            Path(wallet).write_text(json.dumps(first))
            Path(preflight).write_text(json.dumps({'status': 'AWAITING_SCHEMA_VALIDATION'}))
            second = paper.update(wallet, start, preflight)
            self.assertEqual(second['cash_eur'], 95)
            self.assertEqual(second['closed'], first['closed'])
            self.assertFalse(second['paper_entries_enabled'])
            self.assertFalse(second['observations'][-1]['market_observation'])

    def test_corrupt_wallet_is_not_replaced_by_seed(self):
        with tempfile.TemporaryDirectory() as directory:
            wallet = os.path.join(directory, 'wallet.json')
            Path(wallet).write_text('{}')
            with self.assertRaises(ValueError):
                paper.update(wallet, paper.SEED, 'missing.json')
            self.assertEqual(Path(wallet).read_text(), '{}')


if __name__ == '__main__':
    unittest.main()
