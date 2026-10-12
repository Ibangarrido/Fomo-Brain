import io
import json
import unittest
from unittest.mock import Mock
import jupiter_exit_diagnostic as j

SOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


class JupiterExitDiagnosticTests(unittest.TestCase):
    def test_valid_quote_is_indicative_not_executable(self):
        class Response(io.BytesIO):
            pass
        payload = {"inputMint": SOL, "outputMint": USDC, "outAmount": "100000",
                   "priceImpactPct": "0.1", "routePlan": [{}]}
        calls = []
        def opener(request, timeout):
            calls.append(request)
            return Response(json.dumps(payload).encode())
        result = j.quote(SOL, USDC, 1000000, opener=opener)
        self.assertEqual(result["status"], "INDICATIVE_ONLY")
        self.assertFalse(result["executable_verified"])
        self.assertFalse(result["trade_enabled"])
        self.assertEqual(calls[0].get_method(), "GET")
        self.assertNotIn("/swap/v1/swap", calls[0].full_url)

    def test_invalid_inputs_never_contact_network(self):
        opener = Mock()
        for mint, amount in (("bad", 10), (SOL, 0), (SOL, True)):
            with self.assertRaises(ValueError):
                j.quote(mint, USDC, amount, opener=opener)
        opener.assert_not_called()

    def test_wrong_mint_or_missing_route_value_rejected(self):
        class Response(io.BytesIO):
            pass
        for payload in ({"inputMint": USDC, "outputMint": SOL, "outAmount": "10"},
                        {"inputMint": SOL, "outputMint": USDC, "outAmount": "0"}):
            with self.assertRaises(ValueError):
                j.quote(SOL, USDC, 1000, opener=lambda *a, **k: Response(json.dumps(payload).encode()))


if __name__ == "__main__":
    unittest.main()
