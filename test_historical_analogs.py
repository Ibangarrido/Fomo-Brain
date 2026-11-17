import unittest
from historical_analogs import analyze


def candles(n):
    return [[i*3600000,100,101,99,100+i*0.001,10,(i+1)*3600000-1] for i in range(n)]

class AnalogsTests(unittest.TestCase):
    def test_outcomes_precede_current_window_and_do_not_overlap(self):
        rows = candles(512)
        r = analyze(rows)
        self.assertEqual(r['status'],'DESCRIPTIVE_ONLY')
        ends = sorted(c['input_end_ms'] for c in r['cases'])
        self.assertTrue(all(b-a >= 24*3600000 for a,b in zip(ends,ends[1:])))
        query_start = rows[-24][0]
        self.assertTrue(all(c['outcome_end_ms'] <= query_start for c in r['cases']))
        self.assertFalse(r['used_for_entries'])
        self.assertFalse(r['calibrated_probability'])

    def test_missing_data_produces_no_percentage(self):
        r = analyze(candles(60))
        self.assertEqual(r['status'],'INSUFFICIENT_DATA')
        self.assertNotIn('historical_positive_fraction', r)

    def test_bad_price_or_gap_rejected(self):
        rows = candles(100)
        rows[50][4] = float('nan')
        with self.assertRaises(ValueError): analyze(rows)
        rows = candles(100)
        del rows[50]
        with self.assertRaises(ValueError): analyze(rows)

    def test_costs_are_charged(self):
        rows = candles(512)
        for r in rows: r[4] = 100
        r=analyze(rows)
        self.assertAlmostEqual(r['mean_net_return'], -0.004)

if __name__ == '__main__': unittest.main()
