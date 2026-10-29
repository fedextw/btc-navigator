import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from agent_stage_four_integrated_audit import audit_delivery

class StageFourIntegratedAuditTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
    def make_research(self):
        report={"schema":"agent-orchestrator-v1","paper_only":True,
                "live_trading_authorized":False,"candidate_count":1,
                "candidates":[{"status":"rejected"}],"selected":None}
        raw=json.dumps(report).encode()
        path=self.root/(hashlib.sha256(raw).hexdigest()+".json")
        path.write_bytes(raw)
        check=self.root/"markets"/"BTCUSDT"/"1h"/"stage4-checkpoint.json"
        check.parent.mkdir(parents=True)
        check.write_text(json.dumps({"schema":"agent-stage4-checkpoint-v1",
              "symbol":"BTCUSDT","interval":"1h","status":"completed","slot":"SLOT01",
              "paper_only":True,"live_trading_authorized":False,
              "report_path":str(path)}))
        return path
    def rotation(self,status):
        path=self.root/"stage4-universe-cursor.json"
        path.write_text(json.dumps({"schema":"agent-stage4-universe-cursor-v1",
              "status":status,"slot":"SLOT01","symbols":["BTCUSDT"],"paper_only":True,
              "live_trading_authorized":False}))
    def test_empty_cannot_claim_completion(self):
        result=audit_delivery(self.root)
        self.assertFalse(result["engineering_evidence_valid"])
        self.assertIn("missing_rotation_checkpoint",result["issues"])
        self.assertIn("no_verified_research_reports",result["issues"])
    def test_integrated_saved_evidence_passes_engineering_only(self):
        self.make_research()
        self.rotation("completed")
        result=audit_delivery(self.root)
        self.assertTrue(result["engineering_evidence_valid"])
        self.assertEqual(result["reports_verified"],1)
        self.assertFalse(result["forward_performance_validated"])
        self.assertFalse(result["profitability_proven"])
        self.assertFalse(result["live_trading_authorized"])
    def test_interrupted_rotation_fails_even_if_market_report_exists(self):
        self.make_research()
        self.rotation("reserved")
        result=audit_delivery(self.root)
        self.assertFalse(result["engineering_evidence_valid"])
        self.assertIn("rotation_not_completed",result["issues"])
    def test_other_slot_research_cannot_pass_current_rotation(self):
        self.make_research()
        self.rotation("completed")
        check=self.root/"markets"/"BTCUSDT"/"1h"/"stage4-checkpoint.json"
        entry=json.loads(check.read_text())
        entry["slot"]="OLD_SLOT"
        check.write_text(json.dumps(entry))
        result=audit_delivery(self.root)
        self.assertFalse(result["engineering_evidence_valid"])
        self.assertIn("rotation_market_evidence_mismatch",result["issues"])
    def test_tampered_report_fails_closed(self):
        path=self.make_research()
        self.rotation("completed")
        path.write_bytes(path.read_bytes()+b"x")
        with self.assertRaisesRegex(ValueError,"fingerprint"):
            audit_delivery(self.root)
if __name__=="__main__":
    unittest.main()
