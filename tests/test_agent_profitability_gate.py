import unittest
from agent_profitability_gate import assess

class ProfitabilityGateTests(unittest.TestCase):
    def test_marginal_or_sparse_strategy_is_rejected(self):
        report=assess({"trades":7,"net_expectancy_r":0.1,"profit_factor":1.2,"max_drawdown_pct":5})
        self.assertFalse(report["eligible"])
        self.assertFalse(report["live_trading_authorized"])

    def test_negative_net_expectancy_is_rejected(self):
        report=assess({"trades":100,"net_expectancy_r":-0.01,"profit_factor":1.3,"max_drawdown_pct":3})
        self.assertFalse(report["eligible"])

    def test_drawdown_and_invalid_values_fail_closed(self):
        self.assertFalse(assess({"trades":100,"net_expectancy_r":0.1,"profit_factor":float("nan"),"max_drawdown_pct":3})["eligible"])
        self.assertFalse(assess({"trades":100,"net_expectancy_r":0.1,"profit_factor":1.3,"max_drawdown_pct":15})["eligible"])

    def test_strong_sample_only_qualifies_for_forward_testing(self):
        report=assess({"trades":40,"net_expectancy_r":0.2,"profit_factor":1.5,"max_drawdown_pct":5})
        self.assertTrue(report["eligible"])
        self.assertEqual(report["next_stage"],"independent_forward_paper_test")
        self.assertFalse(report["live_trading_authorized"])

if __name__=="__main__":
    unittest.main()
