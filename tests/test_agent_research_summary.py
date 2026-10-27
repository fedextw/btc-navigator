import tempfile
import unittest
from pathlib import Path
from agent_research_batch_evidence import save_batch_evidence
from agent_research_summary import summarize_batches

class ResearchSummaryTests(unittest.TestCase):
    def test_cross_symbol_outcomes_are_research_only(self):
        report={"schema":"agent-scheduler-v1","paper_only":True,
                "live_trading_authorized":False,"finished_at":"2026-10-27T00:00:00Z",
                "counts":{"attempted":2,"completed":1},
                "items":[{"symbol":"BTCUSDT","status":"completed",
                          "result":{"status":"rejected","selected":"trend_10_50","bars":350}},
                         {"symbol":"ETHUSDT","status":"skipped","error_type":"DataNotReady"}]}
        with tempfile.TemporaryDirectory() as td:
            save_batch_evidence(td,0,report)
            summary=summarize_batches(td)
            self.assertEqual(summary["symbols_observed"],2)
            self.assertEqual(summary["rejected_research"],1)
            self.assertEqual(summary["by_symbol"]["ETHUSDT"]["skipped"],1)
            self.assertFalse(summary["automatic_promotion_authorized"])
            path=next((Path(td)/"agent-research-batches").glob("*.json"))
            path.write_bytes(path.read_bytes()+b"x")
            with self.assertRaises(ValueError):
                summarize_batches(td)
    def test_empty_safe(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(summarize_batches(td)["symbols_observed"],0)

if __name__=="__main__":
    unittest.main()
