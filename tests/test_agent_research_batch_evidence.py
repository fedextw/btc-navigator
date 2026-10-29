import json
import tempfile
import unittest
from pathlib import Path
from agent_research_batch_evidence import save_batch_evidence

class BatchAuditTests(unittest.TestCase):
    def test_persists_outcomes_with_no_live_permissions(self):
        report={"schema":"agent-scheduler-v1","paper_only":True,
                "live_trading_authorized":False,"finished_at":"2026-10-27T00:00:00Z",
                "counts":{"attempted":2,"completed":1,"waiting":1},
                "items":[{"symbol":"BTCUSDT","status":"completed",
                          "result":{"selected":"trend_10_50","status":"rejected","bars":350}},
                         {"symbol":"ETHUSDT","status":"skipped","error_type":"DataNotReady"}]}
        with tempfile.TemporaryDirectory() as td:
            path=save_batch_evidence(td,3,report)
            self.assertEqual(path,save_batch_evidence(td,3,report))
            data=json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual([x["symbol"] for x in data["items"]],["BTCUSDT","ETHUSDT"])
            self.assertEqual(data["items"][0]["strategy_status"],"rejected")
            self.assertFalse(data["live_trading_authorized"])
            self.assertTrue(path.is_relative_to(Path(td)))
    def test_rejects_unauthorized_or_inconsistent_report(self):
        report={"schema":"agent-scheduler-v1","paper_only":True,
                "live_trading_authorized":True,"counts":{"attempted":0},"items":[]}
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                save_batch_evidence(td,0,report)
            report["live_trading_authorized"]=False
            report["counts"]["attempted"]=5
            with self.assertRaises(ValueError):
                save_batch_evidence(td,0,report)
if __name__=="__main__":
    unittest.main()
