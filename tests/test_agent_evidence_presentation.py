import tempfile
import unittest
from agent_research_panel import load_status
from agent_research_scheduler import write_status

class EvidencePresentationTests(unittest.TestCase):
    def test_evidence_not_mislabeled_as_live_profitability(self):
        with tempfile.TemporaryDirectory() as td:
            report={"schema":"agent-scheduler-v1","phase":"completed",
                    "live_trading_authorized":False,"paper_only":True,
                    "items":[{"symbol":"BTCUSDT","status":"completed","at":"2026-10-25T00:00:00Z",
                              "result":{"status":"research_candidate","selected":"trend_10_50",
                                        "profitability_evidence":{"eligible":True,"live_trading_authorized":False},
                                        "heldout_metrics":{"trades":24,"net_expectancy_r":0.15}}}]}
            write_status(td,report)
            row=load_status(td)["items"][0]
            self.assertEqual(row["profitability_gate"],"等待獨立前向模擬")
            self.assertEqual(row["heldout_trades"],24)
            self.assertEqual(row["net_expectancy_r"],0.15)

    def test_missing_gate_is_not_a_pass(self):
        with tempfile.TemporaryDirectory() as td:
            write_status(td,{"schema":"agent-scheduler-v1","phase":"completed",
                "live_trading_authorized":False,"items":[{"symbol":"ETHUSDT","status":"completed",
                    "result":{"status":"rejected"}}]})
            self.assertEqual(load_status(td)["items"][0]["profitability_gate"],"尚無審核")

if __name__=="__main__":
    unittest.main()
