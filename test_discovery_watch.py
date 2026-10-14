"""Offline regression tests for Discovery Watch; no external market calls."""
import unittest
from datetime import datetime, timedelta, timezone
import discovery_watch as d

class DiscoveryTests(unittest.TestCase):
    def row(self, **overrides):
        attrs = {'address':'poolA','pool_created_at':'2026-10-14T00:00:00Z',
                 'base_token_price_usd':'0.01','reserve_in_usd':'9000',
                 'volume_usd':{'m5':'2000'},
                 'transactions':{'m5':{'buys':12,'sells':8}},
                 'price_change_percentage':{'h1':'5'}}
        attrs.update(overrides)
        return d.evaluate({'data':[{'attributes':attrs}]})[0]

    def test_valid_candidate(self):
        self.assertTrue(self.row()['watch'])

    def test_missing_price_rejected(self):
        self.assertIn('missing_valid_price', self.row(base_token_price_usd=None)['reasons'])

    def test_missing_hourly_change_rejected(self):
        self.assertIn('missing_gain_1h', self.row(price_change_percentage={})['reasons'])

    def test_near_miss_tracked_without_entry(self):
        row = self.row(reserve_in_usd='7000')
        self.assertFalse(row['watch'])
        h = d.history_update({}, [row], '2026-10-14T00:00:00+00:00')
        self.assertIn('poolA', h)
        self.assertFalse(row['paper_entry'])

    def test_future_only_outcomes(self):
        start = datetime(2026,10,14,tzinfo=timezone.utc)
        prices = [1, 1.10, 1.20, 1.30, 1.40]
        history = {'poolA': {'samples': [
            {'at':(start+timedelta(minutes=15*i)).isoformat(),
             'price_usd':price,'liquidity_usd':9000}
            for i,price in enumerate(prices)]}}
        result = d.pattern_outcomes(history)
        self.assertEqual(result['two_rising_observations:15m']['evaluated'], 2)
        self.assertEqual(result['two_rising_observations:15m']['positive'], 2)

    def test_no_backfill(self):
        row = self.row()
        h = d.history_update({}, [row], '2026-10-14T00:00:00+00:00')
        self.assertEqual(len(h['poolA']['samples']), 1)
        self.assertEqual(d.pattern_outcomes(h), {})

if __name__ == '__main__':
    unittest.main()
