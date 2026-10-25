import json
import tempfile
import unittest
from pathlib import Path
from agent_forward_register import register_qualified

def report():
    return {"schema":"agent-cycle-v1","paper_status":"research_candidate",
            "live_trading_authorized":False,"selected":"trend_8_30",
            "profitability_evidence":{"eligible":True},
            "config":{"heldout_end":"2026-10-24T00:00:00Z"},
            "source":{"symbol":"BTCUSDT","interval":"1h","mode":"live"}}

class ForwardRegistrationTests(unittest.TestCase):
    def test_enrolls_eligible_once_across_retries(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)/"agent-cycles";folder.mkdir()
            (folder/"example.json").write_text(json.dumps(report()),encoding="utf-8")
            first=register_qualified(td,enrolled_at="2026-10-25T00:00:00Z")
            second=register_qualified(td,enrolled_at="2026-10-26T00:00:00Z")
            self.assertEqual(first["registered"],1)
            self.assertEqual(second["existing"],1)
            self.assertEqual(len(list((Path(td)/"agent-forward").glob("*.json"))),1)
            self.assertFalse(first["live_trading_authorized"])

    def test_rejects_failed_and_future_cutoff(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)/"agent-cycles";folder.mkdir()
            failed=report();failed["profitability_evidence"]["eligible"]=False
            (folder/"a.json").write_text(json.dumps(failed),encoding="utf-8")
            bad=report();bad["config"]["heldout_end"]="2026-10-27T00:00:00Z"
            (folder/"b.json").write_text(json.dumps(bad),encoding="utf-8")
            outcome=register_qualified(td,enrolled_at="2026-10-25T00:00:00Z")
            self.assertEqual(outcome["rejected"],2)
            self.assertEqual(outcome["registered"],0)

if __name__=="__main__":
    unittest.main()
