import unittest
from datetime import datetime, timedelta, timezone
from market_structure_audit import report

NOW=datetime(2026,10,26,18,tzinfo=timezone.utc)

def sample(*, price=1.3, liquidity=110, ratio=.7, cohort="automatic_prospective", pair="pool"):
    return {"cohort":cohort,"symbol":"TEST",
            "first":{"pair":"pool","received_at":(NOW-timedelta(minutes=20)).isoformat(),"price":1,"liquidity":100},
            "last":{"pair":pair,"received_at":NOW.isoformat(),"price":price,
                    "liquidity":liquidity,"buy_ratio5m":ratio}}

class MarketStructureTests(unittest.TestCase):
    def test_uptrend_is_not_whale_confirmation(self):
        r=report({"a":sample()},NOW)
        self.assertEqual(r["counts"]["PRICE_UP_WITH_LIQUIDITY_AND_BUY_COUNT"],1)
        self.assertFalse(r["whale_wallets_verified"])
        self.assertFalse(r["entry_authorized"])
    def test_crash_and_exclusions(self):
        r=report({"a":sample(price=.7,liquidity=80),
                  "b":sample(cohort="manual_after_event"),
                  "c":sample(pair="different")},NOW)
        self.assertEqual(r["counts"]["PRICE_DROP_AND_LIQUIDITY_CONTRACTION"],1)
        self.assertEqual(r["counts"]["retrospective_excluded"],1)
        self.assertEqual(r["counts"]["missing_or_changed_pair"],1)
    def test_buy_count_not_dollar_flow(self):
        r=report({"a":sample(ratio=.4)},NOW)
        self.assertEqual(r["counts"]["UNCLASSIFIED"],1)
        self.assertIsNone(r["whale_buy_sell_usd"])

if __name__=="__main__":
    unittest.main()
