import unittest
from brain_v2_radar import assess

class RadarTests(unittest.TestCase):
    def check(self, expected, **changes):
        data = dict(volume_5m=600, previous_volume_5m=200, buyers_5m=30,
                    previous_buyers_5m=10, liquidity=8000, change_5m_pct=8,
                    change_1h_pct=20, quote_age_seconds=15)
        data.update(changes)
        self.assertEqual(assess(**data), expected)
    def test_early(self): self.check("EARLY_WATCH")
    def test_late(self): self.check("LATE_SPIKE", change_1h_pct=150)
    def test_spike(self): self.check("LATE_SPIKE", change_5m_pct=30)
    def test_stale(self): self.check("STALE_DATA", quote_age_seconds=61)
    def test_missing(self): self.check("UNKNOWN_DATA", liquidity=None)
    def test_nan(self): self.check("UNKNOWN_DATA", volume_5m=float("nan"))
    def test_low_liquidity(self): self.check("LOW_LIQUIDITY", liquidity=4999)
    def test_baseline(self): self.check("INSUFFICIENT_BASELINE", previous_buyers_5m=0)
    def test_no_acceleration(self): self.check("MONITOR", volume_5m=300)
    def test_negative(self): self.check("INVALID_DATA", buyers_5m=-1)
