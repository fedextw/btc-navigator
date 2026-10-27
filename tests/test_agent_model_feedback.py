import unittest
from agent_model_feedback import feedback_context

class FeedbackTests(unittest.TestCase):
    def baseline(self):
        return {"schema":"agent-orchestrator-v1","paper_only":True,
                "live_trading_authorized":False,"dataset_sha256":"a"*64,
                "candidates":[{"strategy":"trend","status":"rejected",
                "validation":{"net_expectancy_r":-0.01,"max_drawdown_pct":3.0,
                "trades":10,"profit_factor":0.7},
                "trades_detail":[{"secret":"must never appear"}]}],
                "heldout":{"private_future":"never expose"}}
    def test_only_validation_evidence_passes_to_model(self):
        result=feedback_context(self.baseline())
        raw=str(result)
        self.assertIn("validation_only_feedback",raw)
        self.assertNotIn("private_future",raw)
        self.assertNotIn("must never appear",raw)
    def test_nan_rejected(self):
        a=self.baseline()
        a["candidates"][0]["validation"]["profit_factor"]=float("nan")
        with self.assertRaises(ValueError):
            feedback_context(a)
    def test_unsafe_lineage_rejected(self):
        a=self.baseline()
        a["live_trading_authorized"]=True
        with self.assertRaises(ValueError):
            feedback_context(a)
if __name__=="__main__":
    unittest.main()
