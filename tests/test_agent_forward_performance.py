import unittest
from test_agent_forward_paper import observations
from agent_forward_paper import simulate

class ForwardPerformanceTests(unittest.TestCase):
    def test_derived_metrics_and_sample_warning(self):
        result=simulate(observations(120),"trend_8_30")
        self.assertEqual(result["evidence_status"],"retrospective_only_not_forward_verified")
        self.assertEqual(result["prospective_eligible_trades"],0)
        self.assertEqual(result["retrospective_only_trades"],result["trades"])
        self.assertGreaterEqual(result["win_rate_pct"],0)
        self.assertLessEqual(result["win_rate_pct"],100)
        self.assertIsNotNone(result["net_expectancy_fraction"])
        self.assertFalse(result["live_trading_authorized"])

    def test_no_trade_does_not_claim_profit_factor(self):
        data=observations(81)
        result=simulate(data,"trend_8_30")
        self.assertEqual(result["trades"],0)
        self.assertIsNone(result["profit_factor"])
        self.assertIsNone(result["win_rate_pct"])
        self.assertIsNone(result["net_expectancy_fraction"])

if __name__=="__main__":
    unittest.main()
