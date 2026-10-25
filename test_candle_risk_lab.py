import unittest
from candle_risk_lab import analyze_candles


def candle(o, c, h=None, l=None, v=100, liquidity=20000):
    return {"open": o, "close": c, "high": h if h is not None else max(o,c),
            "low": l if l is not None else min(o,c), "volume": v,
            "liquidity_usd": liquidity}


class CandleRiskLabTests(unittest.TestCase):
    def test_confirmed_recovery_is_research_only(self):
        candles = [candle(10, 9), candle(9, 8), candle(8, 8.5),
                   candle(8.5, 9.5, v=160), candle(9.5, 11, v=170)]
        result = analyze_candles(candles)
        self.assertEqual(result["status"], "RECOVERY_RESEARCH")
        self.assertFalse(result["entry_authorized"])

    def test_liquidity_drop_overrides_green_candles(self):
        candles = [candle(10, 9), candle(9, 8), candle(8, 8.5),
                   candle(8.5, 9.5, v=160), candle(9.5, 11, v=170, liquidity=2000)]
        self.assertEqual(analyze_candles(candles)["status"], "LIQUIDITY_RISK")

    def test_missing_or_invalid_data_never_signal(self):
        self.assertEqual(analyze_candles([])["status"], "INSUFFICIENT_DATA")
        candles = [candle(10, 9)] * 5
        candles[-1]["volume"] = -1
        self.assertEqual(analyze_candles(candles)["status"], "INVALID_DATA")

    def test_no_recovery(self):
        candles = [candle(10, 9)] * 5
        self.assertEqual(analyze_candles(candles)["status"], "NO_PATTERN")


if __name__ == "__main__":
    unittest.main()
