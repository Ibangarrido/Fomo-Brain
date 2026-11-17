import copy
import unittest
from kronos_paper import settle

class EvaluationTests(unittest.TestCase):
    def test_no_result_before_target_and_no_rewrite(self):
        record = {'target_ms':7200000,'entry_price':100,'predicted_return':0.1,'signal':'LONG'}
        records = [record]
        settle(records, [[0,0,0,0,105,0,3599999]])
        self.assertNotIn('result', record)
        settle(records, [[0,0,0,0,110,0,7199999]])
        self.assertAlmostEqual(record['result']['paper_net_return'], 0.096)
        original = copy.deepcopy(record)
        settle(records, [[0,0,0,0,50,0,7199999]])
        self.assertEqual(record, original)

    def test_cash_and_baseline_costs(self):
        record = {'target_ms':7200000,'entry_price':100,'predicted_return':-0.1,'signal':'CASH'}
        settle([record], [[0,0,0,0,90,0,7199999]])
        self.assertEqual(record['result']['paper_net_return'], 0)
        self.assertAlmostEqual(record['result']['buy_hold_net_return'], -0.104)
        self.assertTrue(record['result']['direction_correct'])

if __name__ == '__main__':
    unittest.main()
