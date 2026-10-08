import unittest
from unittest.mock import patch
from urllib.parse import urlparse, parse_qs

from route_shadow import USDC, RouteShadow, roundtrip_quote

MINT = "HciAVS1urBtboqhLe59HWiMeeN2McEd6y8h4HGkrpump"


class RoundtripTests(unittest.TestCase):
    def provider(self, fail_sell=False, wrong_identity=False, transaction=False):
        calls = []
        def fetch(url):
            q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
            calls.append(q)
            self.assertNotIn("taker", q)
            if len(calls) == 2 and fail_sell:
                raise ValueError("No route")
            return {"inputMint": q["inputMint"],
                    "outputMint": USDC if wrong_identity else q["outputMint"],
                    "inAmount": q["amount"], "swapMode": "ExactIn",
                    "transaction": "unsigned" if transaction else None,
                    "router": "metis", "outAmount": "123456789" if len(calls) == 1 else "4700000",
                    "otherAmountThreshold": "120000000" if len(calls) == 1 else "4600000"}
        return fetch, calls

    def test_exact_buy_quantity_is_used_for_sell(self):
        fetch, calls = self.provider()
        r = roundtrip_quote(MINT, fetch)
        self.assertEqual(calls[0], {"inputMint": USDC, "outputMint": MINT, "amount": "5000000"})
        self.assertEqual(calls[1]["amount"], "123456789")
        self.assertEqual(r["returned_usdc"], 4.7)
        self.assertAlmostEqual(r["quoted_roundtrip_loss_pct"], 6)
        self.assertFalse(r["execution_verified"])
        self.assertIsNone(r["network_cost_usdc"])

    def test_missing_sell_never_creates_a_valuation(self):
        fetch, _ = self.provider(fail_sell=True)
        r = roundtrip_quote(MINT, fetch)
        self.assertEqual(r["failure_stage"], "sell_quote")
        self.assertEqual(r["status"], "UNAVAILABLE")
        self.assertIsNone(r["returned_usdc"])
        self.assertIsNone(r["quoted_roundtrip_loss_pct"])

    def test_mismatched_identity_stops_before_sell(self):
        fetch, calls = self.provider(wrong_identity=True)
        self.assertEqual(roundtrip_quote(MINT, fetch)["status"], "UNAVAILABLE")
        self.assertEqual(len(calls), 1)

    def test_transaction_response_rejected(self):
        fetch, calls = self.provider(transaction=True)
        self.assertEqual(roundtrip_quote(MINT, fetch)["status"], "UNAVAILABLE")
        self.assertEqual(len(calls), 1)

    def test_roundtrip_shares_request_spacing_and_stop(self):
        watcher = RouteShadow(fetch=lambda url: {"ok": True})
        watcher.next_jupiter_request = 103
        with patch("route_shadow.time.monotonic", return_value=100), \
                patch.object(watcher.stop_event, "wait", return_value=False) as wait:
            self.assertEqual(watcher.paced_jupiter_fetch("url"), {"ok": True})
            wait.assert_called_once_with(3)
        watcher.stop_event.set()
        with self.assertRaises(ValueError):
            watcher.paced_jupiter_fetch("url")
