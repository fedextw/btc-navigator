import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from agent_stage_three_acceptance import verify_stage_three

class StageThreeAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root=Path(self.t.name)
    def report(self,**changes):
        doc={"schema":"agent-orchestrator-v1","source":"external_ai_specifications",
             "paper_only":True,"live_trading_authorized":False,
             "proposal_model_id":"offline-stub","model_response_sha256":"b"*64,
             "cost_fraction":.0014,"dataset_latest_utc":"2026-01-10T00:00:00+00:00",
             "validation_start_utc":"2026-01-07T00:00:00+00:00",
             "parent_report_sha256":None,"model_feedback_used":False}
        doc.update(changes)
        return doc
    def save(self,doc):
        raw=(json.dumps(doc,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\\n").encode()
        name=hashlib.sha256(raw).hexdigest()+".json"
        path=self.root/name
        path.write_bytes(raw)
        return path
    def two(self):
        first=self.report()
        parent=hashlib.sha256(json.dumps(first,sort_keys=True,ensure_ascii=False,
                                          allow_nan=False).encode()).hexdigest()
        second=self.report(parent_report_sha256=parent,model_feedback_used=True,
            validation_start_utc="2026-02-10T00:00:00+00:00",
            dataset_latest_utc="2026-02-15T00:00:00+00:00")
        return [self.save(first),self.save(second)]
    def test_cannot_claim_completion_from_offline_stubs(self):
        result=verify_stage_three(self.two())
        self.assertFalse(result["accepted"])
        self.assertIn("Live LLM provider end-to-end verification outstanding",result["issues"])
    def test_independent_attestation_with_complete_evidence(self):
        result=verify_stage_three(self.two(),live_provider_verified=True)
        self.assertTrue(result["accepted"])
        self.assertEqual(result["verified_reports"],2)
    def test_mismatched_lineage_rejected(self):
        first,second=self.two()
        doc=json.loads(second.read_text())
        doc["parent_report_sha256"]="0"*64
        rejected=verify_stage_three([first,self.save(doc)],live_provider_verified=True)
        self.assertFalse(rejected["accepted"])
    def test_tampered_report_rejected(self):
        first,second=self.two()
        first.write_bytes(first.read_bytes()+b" ")
        self.assertFalse(verify_stage_three([first,second],live_provider_verified=True)["accepted"])
if __name__=="__main__":
    unittest.main()
