import unittest
from unittest.mock import patch
import solana_float_watch as watch

class FloatWatchTests(unittest.TestCase):
    def test_read_only_allowlist(self):
        with self.assertRaises(ValueError):
            watch.rpc_read("sendTransaction", [])

    def test_bounded_pages(self):
        for n in (0, 101, True):
            with self.assertRaises(ValueError):
                watch.token_signatures(limit=n)

    def test_no_wallet_attribution_even_with_mint_transaction(self):
        tx = {"slot": 123, "blockTime": 1790000000,
              "transaction": {"message": {"accountKeys": [
                  {"pubkey": "someFeePayer", "signer": True}]}}}
        result = watch.classify_observation("sig1", tx)
        self.assertIsNone(result["trader"])
        self.assertFalse(result["paper_entry"])
        self.assertEqual(result["status"], "PUBLIC_TRANSACTION_UNATTRIBUTED")

    def test_missing_transaction_fails_closed(self):
        result = watch.classify_observation("sig1", None)
        self.assertEqual(result["status"], "UNVERIFIED_TRANSACTION")
        self.assertFalse(result["paper_entry"])

    def test_rpc_signatures_bounded(self):
        with patch.object(watch, "rpc_read", return_value=[{"signature": "sig1"}]) as rpc:
            result = watch.token_signatures(limit=5)
            self.assertEqual(result[0]["signature"], "sig1")
            self.assertEqual(rpc.call_args.args[0], "getSignaturesForAddress")

if __name__ == "__main__":
    unittest.main()
