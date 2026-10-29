import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from agent_stage_four_paper_review import review

class PaperReviewTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        report={"schema":"agent-orchestrator-v1","paper_only":True,
                "live_trading_authorized":False,"candidate_count":1,
                "candidates":[{"status":"validation_pass"}],"selected":"agent_trend_8_30"}
        raw=json.dumps(report).encode()
        sha=hashlib.sha256(raw).hexdigest()
        self.path=self.root/(sha+".json")
        self.path.write_bytes(raw)
        check=self.root/"markets"/"BTCUSDT"/"1h"/"stage4-checkpoint.json"
        check.parent.mkdir(parents=True)
        check.write_text(json.dumps({"schema":"agent-stage4-checkpoint-v1",
            "paper_only":True,"live_trading_authorized":False,"symbol":"BTCUSDT",
            "interval":"1h","status":"completed","report_path":str(self.path)}))
        self.paper=self.root/"paper.json"
        self.payload={"schema":"agent-forward-paper-v1","symbol":"BTCUSDT",
                      "live_trading_authorized":False,"not_actual_fills":True,
                      "execution_verified":False,"research_sha256":sha,
                      "prospective_eligible_trades":42,"evidence_status":"requires_independent_review",
                      "prospective_paper_net_return_pct":1.25}
        self.paper.write_text(json.dumps(self.payload))
    def test_report_and_forward_are_separate_evidence(self):
        value=review(self.root,paper_summaries={"BTCUSDT":str(self.paper)})
        self.assertEqual(value["prospective_paper_markets"],1)
        self.assertEqual(value["markets"][0]["observed_forward_trades"],42)
        self.assertFalse(value["profitability_proven"])
        self.assertFalse(value["automatic_promotion"])
        self.assertFalse(value["live_trading_authorized"])
    def test_reject_report_mismatch(self):
        self.payload["research_sha256"]="f"*64
        self.paper.write_text(json.dumps(self.payload))
        with self.assertRaisesRegex(ValueError,"another research"):
            review(self.root,paper_summaries={"BTCUSDT":str(self.paper)})
    def test_missing_paper_cannot_claim_prospective_trades(self):
        result=review(self.root)
        self.assertEqual(result["prospective_paper_markets"],0)
        self.assertEqual(result["markets"][0]["forward_evidence"],"not_submitted")
if __name__=="__main__":
    unittest.main()
