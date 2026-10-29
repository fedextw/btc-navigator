import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from agent_forward_freeze import freeze_candidate

class FrozenForwardResearchTests(unittest.TestCase):
    def test_research_candidate_is_frozen_once_with_cutoff(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            report={"config":{"heldout_end":"2026-10-01T00:00:00+00:00"},
                    "dataset_sha256":"a"*64}
            report_path=root/"cycle.json"
            report_path.write_text(json.dumps(report),encoding="utf-8")
            candidate={"status":"research_candidate","selected":"trend_10_50",
                       "report_path":str(report_path),
                       "source":{"symbol":"BTCUSDT","interval":"1h","mode":"live"},
                       "live_trading_authorized":False}
            first=freeze_candidate(root,candidate)
            second=freeze_candidate(root,candidate)
            self.assertEqual(first,second)
            self.assertEqual(first["status"],"frozen_for_future_paper_review")
            path=next((root/"agent-frozen-paper-candidates").glob("*.json"))
            record=json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(record["automatic_promotion_authorized"])
            self.assertEqual(record["historical_cutoff_utc"],report["config"]["heldout_end"])
            self.assertEqual(record["reference_report_sha256"],hashlib.sha256(report_path.read_bytes()).hexdigest())

    def test_rejected_and_demo_not_frozen(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(freeze_candidate(td,{"status":"rejected"}))
            with self.assertRaises(ValueError):
                freeze_candidate(td,{"status":"research_candidate",
                                     "selected":"trend_8_30",
                                     "live_trading_authorized":False})

if __name__=="__main__":
    unittest.main()
