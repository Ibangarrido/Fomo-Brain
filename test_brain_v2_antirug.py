import unittest
from brain_v2_antirug import assess

class AntiRugTests(unittest.TestCase):
    def case(self,**kw):
        return assess(**dict(dict(liquidity_usd=10000,previous_liquidity_usd=10000,top10_pct=20,mint_authority_active=False,freeze_authority_active=False,route_verified=True,evidence_verified=True,age_seconds=10),**kw))
    def test_no_flag(self):
        self.assertEqual(self.case()["status"],"NO_FLAG_OBSERVED")
    def test_low_liquidity(self):
        self.assertIn("LOW_LIQUIDITY",self.case(liquidity_usd=100)["risks"])
    def test_withdrawal(self):
        self.assertIn("LIQUIDITY_DROP",self.case(liquidity_usd=7000)["risks"])
    def test_concentration(self):
        self.assertIn("CONCENTRATED_HOLDERS",self.case(top10_pct=50)["risks"])
    def test_mint(self):
        self.assertIn("MINT_AUTHORITY_ACTIVE",self.case(mint_authority_active=True)["risks"])
    def test_freeze(self):
        self.assertIn("FREEZE_AUTHORITY_ACTIVE",self.case(freeze_authority_active=True)["risks"])
    def test_route(self):
        self.assertEqual(self.case(route_verified=False)["status"],"UNKNOWN_BLOCK")
    def test_stale(self):
        self.assertEqual(self.case(age_seconds=61)["status"],"UNKNOWN_BLOCK")
    def test_missing(self):
        self.assertEqual(assess()["status"],"UNKNOWN_BLOCK")
    def test_invalid(self):
        self.assertEqual(self.case(top10_pct=float("nan"))["status"],"UNKNOWN_BLOCK")
    def test_no_orders(self):
        self.assertEqual(self.case()["orders"],[])
