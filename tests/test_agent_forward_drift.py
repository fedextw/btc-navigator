import unittest
from agent_forward_drift import assess_forward_drift

class DriftTests(unittest.TestCase):
    def setUp(self):
        self.ref={"heldout_end_utc":"2026-01-01T00:00:00+00:00"}
        self.new={"first_signal_utc":"2026-01-02T00:00:00+00:00",
                  "trades":31,"net_expectancy_r":-0.001,
                  "max_drawdown_pct":5.,"costs_included":True,"paper_only":True}

    def test_deterioration_requires_review_not_auto_promotion(self):
        result=assess_forward_drift(self.ref,self.new)
        self.assertEqual(result["status"],"review_strategy_deterioration")
        self.assertFalse(result["automatic_promotion_authorized"])
        self.assertFalse(result["live_trading_authorized"])

    def test_small_sample_waits(self):
        self.new["trades"]=10
        self.assertEqual(assess_forward_drift(self.ref,self.new)["status"],"insufficient_forward_evidence")

    def test_newer_unevaluated_or_uncosted_data_fail_closed(self):
        self.new["first_signal_utc"]="2025-12-31T23:59:59+00:00"
        with self.assertRaises(ValueError):
            assess_forward_drift(self.ref,self.new)
        self.new["first_signal_utc"]="2026-01-02T00:00:00+00:00"
        self.new["costs_included"]=False
        with self.assertRaises(ValueError):
            assess_forward_drift(self.ref,self.new)

if __name__=="__main__":
    unittest.main()
