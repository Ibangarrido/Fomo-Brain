import unittest
from trading_learning import summarize


class LearningReportTests(unittest.TestCase):
    def test_same_pair_market_requalification_only(self):
        state = {"tokens": {
            "a": {"cohort": "automatic_prospective",
                  "first": {"entry_rejections": ["ratio"]},
                  "second_look_history": [{"market_gates_pass": True,
                      "checks": {"same_pair_as_rejection": True}}]},
            "b": {"cohort": "automatic_prospective",
                  "first": {"entry_rejections": ["ratio"]},
                  "second_look_history": [{"market_gates_pass": True,
                      "checks": {"same_pair_as_rejection": False}}]},
            "c": {"cohort": "manual_after_event",
                  "first": {"entry_rejections": ["ratio"]},
                  "second_look_history": [{"market_gates_pass": True,
                      "checks": {"same_pair_as_rejection": True}}]}
        }}
        report = summarize(state)
        self.assertEqual(report["rejected_automatic_observed"], 2)
        self.assertEqual(report["requalified_market_only_same_pair"], 1)
        self.assertEqual(report["real_orders"], 0)

    def test_missing_data_does_not_count_as_requalified(self):
        self.assertEqual(summarize({"tokens": {"x": {
            "cohort": "automatic_prospective",
            "first": {"entry_rejections": ["volume"]},
            "second_look_history": [{"market_gates_pass": None}]
        }}})["requalified_market_only_same_pair"], 0)


if __name__ == "__main__":
    unittest.main()
