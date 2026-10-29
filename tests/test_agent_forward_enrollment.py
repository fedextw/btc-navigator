import tempfile
import unittest
import json
from pathlib import Path
from agent_forward_enrollment import enroll, eligible_future_candle

def sample():
    return {"schema":"agent-cycle-v1","paper_status":"research_candidate",
            "live_trading_authorized":False,"selected":"trend_8_30",
            "profitability_evidence":{"eligible":True},
            "config":{"heldout_end":"2026-10-24T00:00:00+00:00"}}

class PaperForwardEnrollmentTests(unittest.TestCase):
    def test_future_only_and_repeat_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            p=enroll(sample(),"BTCUSDT",td,enrolled_at="2026-10-25T00:00:00+00:00")
            self.assertEqual(p,enroll(sample(),"BTCUSDT",td,enrolled_at="2026-10-25T00:00:00+00:00"))
            row=json.loads(p.read_text(encoding="utf-8"))
            self.assertFalse(eligible_future_candle(row,"2026-10-25T00:00:00Z"))
            self.assertTrue(eligible_future_candle(row,"2026-10-25T01:00:00Z"))
            self.assertFalse(row["live_trading_authorized"])
            self.assertEqual(len(list(Path(td).glob("*.json"))),1)

    def test_cannot_backdate_or_promote_failed_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                enroll(sample(),"BTCUSDT",td,enrolled_at="2026-10-23T00:00:00Z")
            bad=sample()
            bad["profitability_evidence"]["eligible"]=False
            with self.assertRaises(ValueError):
                enroll(bad,"BTCUSDT",td,enrolled_at="2026-10-25T00:00:00Z")
            self.assertEqual(list(Path(td).iterdir()),[])

if __name__=="__main__":
    unittest.main()
