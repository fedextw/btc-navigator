import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from agent_stage_four_evidence import inspect

class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.check=self.root/"markets"/"BTCUSDT"/"1h"/"stage4-checkpoint.json"
        self.check.parent.mkdir(parents=True)
    def test_verified_report_and_unfinished_slot(self):
        report={"schema":"agent-orchestrator-v1","paper_only":True,
                "live_trading_authorized":False,"candidate_count":1,
                "candidates":[{"status":"rejected"}],"selected":None}
        blob=json.dumps(report).encode()
        file=self.root/(hashlib.sha256(blob).hexdigest()+".json")
        file.write_bytes(blob)
        checkpoint={"schema":"agent-stage4-checkpoint-v1","paper_only":True,
                    "live_trading_authorized":False,"symbol":"BTCUSDT",
                    "interval":"1h","slot":"slot1","status":"completed",
                    "report_path":str(file)}
        self.check.write_text(json.dumps(checkpoint))
        verified=inspect(self.root)
        self.assertEqual(verified["verified_reports"],1)
        self.assertEqual(verified["markets"][0]["qualified"],0)
        self.assertFalse(verified["profitability_proven"])
        checkpoint["status"]="reserved"
        self.check.write_text(json.dumps(checkpoint))
        waiting=inspect(self.root)
        self.assertEqual(waiting["requires_manual_review"],1)
        self.assertEqual(waiting["verified_reports"],0)
    def test_tampered_report_rejected(self):
        report={"schema":"agent-orchestrator-v1","paper_only":True,
                "live_trading_authorized":False,"candidate_count":0,"candidates":[]}
        blob=json.dumps(report).encode()
        file=self.root/(hashlib.sha256(blob).hexdigest()+".json")
        file.write_bytes(blob+b"tampered")
        self.check.write_text(json.dumps({"schema":"agent-stage4-checkpoint-v1",
            "paper_only":True,"live_trading_authorized":False,"symbol":"BTCUSDT",
            "interval":"1h","status":"completed","report_path":str(file)}))
        with self.assertRaisesRegex(ValueError,"fingerprint"):
            inspect(self.root)
if __name__=="__main__":
    unittest.main()
