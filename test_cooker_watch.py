import unittest
from cooker_watch import WALLET, classify, collect


def transaction(signer=True, owner=WALLET, failed=None):
    return {'slot': 1, 'blockTime': 100, 'transaction': {'message': {
        'accountKeys': [{'pubkey': WALLET, 'signer': signer}]}}, 'meta': {
        'err': failed, 'preTokenBalances': [], 'postTokenBalances': [
            {'owner': owner, 'mint': 'TOKEN', 'uiTokenAmount': {'amount': '1000001', 'decimals': 6}}]}}


class WatchTests(unittest.TestCase):
    def test_unsigned_transfer_is_not_buy(self):
        event = classify(transaction(False), 'a')
        self.assertEqual(event['kind'], 'UNSIGNED_OR_OTHER')
        self.assertFalse(event['paper_fill'])

    def test_signed_change_requires_verification(self):
        event = classify(transaction(), 'a')
        self.assertTrue(event['requires_swap_verification'])
        self.assertEqual(event['token_deltas'], {'TOKEN': '1.000001'})

    def test_other_owner_excluded(self):
        self.assertEqual(classify(transaction(owner='other'), 'a')['token_deltas'], {})

    def test_failed(self):
        self.assertEqual(classify(transaction(failed={'err': 1}), 'a')['kind'], 'FAILED')

    def test_missing_tx(self):
        with self.assertRaises(ValueError):
            classify(None, 'a')

    def test_baseline_never_replays(self):
        calls = []
        def fetch(method, params):
            calls.append(method)
            return [{'signature': 'a'}]
        state = collect({}, fetch, lambda _: None)
        self.assertEqual(calls, ['getSignaturesForAddress'])
        self.assertEqual(state['cursor'], 'a')
        self.assertEqual(state['events'], [])

    def test_chronological_and_deduplicated(self):
        def fetch(method, params):
            return [{'signature': s} for s in ['c', 'b', 'a']] if method == 'getSignaturesForAddress' else transaction()
        state = {'cursor': 'a', 'events': []}
        collect(state, fetch, lambda _: None)
        self.assertEqual([e['signature'] for e in state['events']], ['b', 'c'])
        collect(state, fetch, lambda _: None)
        self.assertEqual(len(state['events']), 2)
        self.assertEqual(state['new_events'], 0)

    def test_gap_retains_cursor(self):
        state = collect({'cursor': 'a'}, lambda *_: [{'signature': 'b'}], lambda _: None)
        self.assertEqual(state['cursor'], 'a')
        self.assertEqual(state['status'], 'HISTORY_GAP_CURSOR_RETAINED')

    def test_partial_error_retains_cursor_and_completed_events(self):
        def fetch(method, params):
            if method == 'getSignaturesForAddress':
                return [{'signature': s} for s in ['c', 'b', 'a']]
            return transaction() if params[0] == 'b' else None
        state = {'cursor': 'a'}
        with self.assertRaises(ValueError):
            collect(state, fetch, lambda _: None)
        self.assertEqual(state['cursor'], 'a')
        self.assertEqual([e['signature'] for e in state['events']], ['b'])

    def test_wrong_wallet(self):
        with self.assertRaises(ValueError):
            collect({'wallet': 'other'})


if __name__ == '__main__':
    unittest.main()
