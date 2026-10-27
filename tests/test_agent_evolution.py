import unittest
from agent_evolution import evolve

def parent(family="trend", fast=10, slow=50, score=.2):
    return {"spec": {"family":family, "lookback":fast, "slow":slow,
                     "rationale":"research"}, "validation":{
                     "net_expectancy_r":score,"max_drawdown_pct":2.0,"trades":12}}

class EvolutionTests(unittest.TestCase):
    def test_children_are_bounded_and_never_tradable(self):
        report=evolve({"source":"pre_registered_parameter_grammar","candidates":[parent()]})
        self.assertEqual(report["source"], "validation_guided_evolution")
        self.assertEqual(len(report["proposals"]), 2)
        self.assertTrue(report["paper_only"])
        self.assertFalse(report["live_trading_authorized"])
        self.assertEqual(report["status"], "requires_fresh_validation")
    def test_reject_unknown_lineage(self):
        with self.assertRaises(ValueError):
            evolve({"source":"untrusted","candidates":[parent()]})
    def test_reject_missing_evidence(self):
        sample=parent()
        del sample["validation"]["trades"]
        with self.assertRaises(ValueError):
            evolve({"source":"pre_registered_parameter_grammar","candidates":[sample]})
    def test_failure_diagnostics_follow_validation_evidence(self):
        low=parent(score=-0.2)
        low["validation"]["trades"]=3
        risk=parent("breakout",20,0,.1)
        risk["validation"]["max_drawdown_pct"]=18
        report=evolve({"source":"pre_registered_parameter_grammar",
                       "candidates":[low,risk]})
        reasons={x["strategy"]: x["reason"] for x in report["validation_diagnostics"]}
        self.assertEqual(reasons["agent_trend_10_50"],"insufficient_samples")
        self.assertEqual(reasons["agent_breakout_20_0"],"excess_drawdown")
        self.assertIn("上一代診斷", report["proposals"][0]["rationale"])
    def test_invalid_drawdown_rejected(self):
        sample=parent()
        sample["validation"]["max_drawdown_pct"]=-2
        with self.assertRaises(ValueError):
            evolve({"source":"pre_registered_parameter_grammar","candidates":[sample]})
    def test_deterministic(self):
        previous={"source":"pre_registered_parameter_grammar","candidates":[parent(),parent("breakout",20,0)]}
        self.assertEqual(evolve(previous),evolve(previous))
if __name__=="__main__":
    unittest.main()
