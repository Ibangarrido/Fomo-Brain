import contextlib
import copy
import io
import json
import threading
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import fomo_brain as brain
from test_fomo_v8 import pair


class PairBatchTests(unittest.TestCase):
    def setUp(self):
        brain.JSON_CACHE.clear();brain.JSON_RECEIPTS.clear()
        self.rows=[pair(address='a',pool='pa'),pair(address='b',pool='pb')]
        self.ranking=[brain.analizar_par(row) for row in self.rows]
        self.at=datetime.now(timezone.utc);self.clock=100.
    def fetch(self, rows=None, age=0, receipt=True):
        def get(url):
            data={'pairs':copy.deepcopy(self.rows if rows is None else rows)}
            brain.JSON_CACHE[url]=data
            if receipt:
                brain.JSON_RECEIPTS[url]=(data,self.at-timedelta(seconds=age),self.clock-age)
            return data
        return get
    def run_batch(self,fetch):
        with patch.object(brain,'pedir_json',side_effect=fetch) as getter,patch.object(brain.time,'monotonic',return_value=self.clock),contextlib.redirect_stdout(io.StringIO()):
            report=brain.prefetch_entry_pairs(self.ranking)
        return report,getter
    def test_one_request_seeds_two_exact_quotes_with_original_receipt(self):
        report,getter=self.run_batch(self.fetch(age=1))
        self.assertEqual(getter.call_count,1);self.assertEqual(report['seeded'],2)
        self.assertTrue(getter.call_args.args[0].endswith('/solana/pa,pb'))
        with patch.object(brain.time,'monotonic',return_value=self.clock),patch.object(brain.urllib.request,'urlopen',side_effect=AssertionError('unexpected network')):
            for token in self.ranking:
                price,liquidity,row=brain.cotizar_posicion(dict(token))
                self.assertEqual((price,liquidity),(1,20000))
                self.assertEqual(row['_brain_received_at'],(self.at-timedelta(seconds=1)).isoformat())
    def test_wrong_chain_contract_missing_and_ambiguous_rows_are_not_seeded(self):
        for rows in ([dict(self.rows[0],chainId='base')],
                     [dict(self.rows[0],baseToken={'address':'wrong'})],[],
                     [self.rows[0],dict(self.rows[0],priceUsd='2')]):
            with self.subTest(rows=rows):
                brain.JSON_CACHE.clear();brain.JSON_RECEIPTS.clear()
                report,_=self.run_batch(self.fetch(rows=rows))
                self.assertEqual(report['seeded'],0)
                self.assertNotIn('https://api.dexscreener.com/latest/dex/pairs/solana/pa',brain.JSON_CACHE)
    def test_old_or_unproven_receipts_never_get_new_timestamps(self):
        for kwargs in ({'age':4},{'age':-1},{'receipt':False}):
            brain.JSON_CACHE.clear();brain.JSON_RECEIPTS.clear()
            report,_=self.run_batch(self.fetch(**kwargs))
            self.assertEqual(report['seeded'],0);self.assertEqual(report['invalid_receipts'],1)
    def test_final_security_invalidation_requires_single_pair_network_read(self):
        self.run_batch(self.fetch())
        token=self.ranking[0];brain.invalidate_entry_quote(token)
        data={'pairs':[dict(self.rows[0],priceUsd='1.01')]}
        response=io.BytesIO(json.dumps(data).encode())
        with patch.object(brain.urllib.request,'urlopen',return_value=response) as opener,patch.object(brain.time,'monotonic',return_value=self.clock):
            price,_,_=brain.cotizar_posicion(dict(token))
        self.assertEqual(price,1.01);opener.assert_called_once()
        self.assertTrue(opener.call_args.args[0].full_url.endswith('/solana/pa'))
    def test_expired_seed_fetches_again_and_worker_cache_is_separate(self):
        self.run_batch(self.fetch())
        visible=[]
        thread=threading.Thread(target=lambda:visible.append(len(brain.JSON_CACHE)))
        thread.start();thread.join();self.assertEqual(visible,[0])
        response=io.BytesIO(json.dumps({'pairs':[dict(self.rows[0],priceUsd='1.02')]}).encode())
        with patch.object(brain.urllib.request,'urlopen',return_value=response) as opener,patch.object(brain.time,'monotonic',return_value=self.clock+4):
            price,_,_=brain.cotizar_posicion(dict(self.ranking[0]))
        self.assertEqual(price,1.02);opener.assert_called_once()
    def test_http_failure_falls_back_without_seeding_or_wallet_changes(self):
        before=copy.deepcopy(self.ranking)
        report,_=self.run_batch(lambda url: (_ for _ in ()).throw(OSError('failed')))
        self.assertEqual(report['errors'],1);self.assertEqual(report['seeded'],0)
        self.assertEqual(self.ranking,before)
    def test_trumpdollar_exact_watch_is_discovered_without_generic_search_hit(self):
        contract = '5Aa378KvCX3bz2dJ3YncoXijBBVvgvipQAXHWaBNNHRw'
        row = pair(address=contract, pool='trump-pool')
        def source(url):
            if '/latest/dex/search/' in url:
                return {'pairs': []}
            if '/token-profiles/' in url or '/token-boosts/' in url:
                return []
            if '/tokens/v1/solana/' in url:
                return [row] if contract in url else []
            if '/token-pairs/v1/' in url:
                return []
            raise AssertionError('unexpected provider endpoint: ' + url)
        with patch.dict(brain.os.environ, {'BRAIN_WATCH_CONTRACTS': 'solana:' + contract}), \\
             patch.object(brain, 'STUDY_TOKENS', []), \\
             patch.object(brain, 'cargar_memoria', return_value=[]), \\
             patch.object(brain, 'pedir_json', side_effect=source), \\
             contextlib.redirect_stdout(io.StringIO()) as log:
            pairs, sources = brain.descubrir_pares()
        self.assertIn(('solana', 'trump-pool'), pairs)
        self.assertIn('watch:contrato', sources[('solana', 'trump-pool')])
        self.assertIn('RADAR WATCH solana:' + contract + ' | pares=1', log.getvalue())

    def test_request_budget_bounds_candidates_and_chunk_size(self):
        self.ranking=[dict(self.ranking[0],pair='p'+str(i),address='a'+str(i)) for i in range(45)]
        report,getter=self.run_batch(self.fetch(rows=[]))
        self.assertEqual(getter.call_count,2)
        for call in getter.call_args_list:self.assertEqual(len(call.args[0].split('/')[-1].split(',')),10)


if __name__=='__main__':unittest.main()
