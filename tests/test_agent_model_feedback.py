import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from agent_model_feedback import feedback_context, research_with_feedback

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
    def test_no_model_call_when_periods_overlap(self):
        p=self.baseline()
        p["cost_fraction"]=.0014
        p["dataset_latest_utc"]="2026-02-01T00:00:00+00:00"
        bars=[(datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(hours=i),) for i in range(400)]
        with patch("agent_model_feedback.read_candles",return_value=(bars,"newhash")):
            with patch("agent_model_feedback.model_research") as model:
                with self.assertRaisesRegex(ValueError,"overlaps"):
                    research_with_feedback("not_read.csv","out",lambda _: "[]",
                                           model_id="stub",prior=p)
                model.assert_not_called()

    def test_fresh_validation_permits_model_boundary(self):
        p=self.baseline()
        p["cost_fraction"]=.0014
        p["dataset_latest_utc"]="2026-01-01T00:00:00+00:00"
        bars=[(datetime(2026,2,1,tzinfo=timezone.utc)+timedelta(hours=i),) for i in range(400)]
        with patch("agent_model_feedback.read_candles",return_value=(bars,"newhash")):
            with patch("agent_model_feedback.model_research",return_value={"paper_only":True}) as model:
                result=research_with_feedback("not_read.csv","out",lambda _: "[]",
                                               model_id="stub",prior=p)
                self.assertTrue(result["paper_only"])
                self.assertEqual(model.call_count,1)
                lineage=model.call_args.kwargs["parent_report_sha256"]
                self.assertEqual(len(lineage),64)
                self.assertTrue(all(c in "0123456789abcdef" for c in lineage))

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
