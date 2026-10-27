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


    def test_large_gap_resumes_scan_and_decodes_in_bounded_batches(self):
        signatures = ['s' + str(i) for i in range(125, 0, -1)] + ['anchor']
        calls = []
        def fetch(method, params):
            if method == 'getTransaction':
                return transaction()
            opts = params[1]
            calls.append(opts.get('before'))
            offset = signatures.index(opts['before']) + 1 if opts.get('before') else 0
            return [{'signature': s} for s in signatures[offset:offset+20]]
        state = {'cursor': 'anchor', 'events': []}
        collect(state, fetch, lambda _: None)
        self.assertEqual(state['status'], 'HISTORY_CATCHUP_SCANNING')
        self.assertEqual(state['cursor'], 'anchor')
        self.assertEqual(len(state['catchup']['rows']), 100)
        collect(state, fetch, lambda _: None)
        self.assertEqual(calls[5], 's26')
        self.assertEqual(state['status'], 'HISTORY_CATCHUP_DECODING')
        self.assertEqual(len(state['events']), 20)
        self.assertEqual(state['cursor'], 'anchor')
        for _ in range(6):
            collect(state, fetch, lambda _: None)
        self.assertEqual(state['status'], 'SYNCED')
        self.assertEqual(state['cursor'], 's125')
        self.assertNotIn('catchup', state)
        self.assertEqual([e['signature'] for e in state['events']],
                         ['s' + str(i) for i in range(1, 126)])
        self.assertTrue(all(not e['paper_fill'] for e in state['events']))

    def test_decode_retry_preserves_pending_row_without_duplicate(self):
        state = {'cursor': 'a', 'events': []}
        failed = [True]
        def fetch(method, params):
            if method == 'getSignaturesForAddress':
                return [{'signature': s} for s in ['c', 'b', 'a']]
            if params[0] == 'c' and failed[0]:
                return None
            return transaction()
        with self.assertRaises(ValueError):
            collect(state, fetch, lambda _: None)
        failed[0] = False
        collect(state, fetch, lambda _: None)
        self.assertEqual(state['cursor'], 'c')
        self.assertEqual([e['signature'] for e in state['events']], ['b', 'c'])

    def test_wrong_wallet(self):
        with self.assertRaises(ValueError):
            collect({'wallet': 'other'})


if __name__ == '__main__':
    unittest.main()
