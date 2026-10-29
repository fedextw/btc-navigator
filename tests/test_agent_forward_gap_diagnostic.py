import json
import tempfile
import unittest
from pathlib import Path
from agent_forward_gap_diagnostic import diagnose

class ForwardGapDiagnosticTests(unittest.TestCase):
    def test_detects_saved_missing_hour_without_repair(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            folder=root/"agent-forward";folder.mkdir()
            entry={"schema":"agent-forward-enrollment-v1","symbol":"BTCUSDT",
                   "strategy":"trend_8_30","research_sha256":"fp123",
                   "live_trading_authorized":False}
            (folder/"enroll.json").write_text(json.dumps(entry),encoding="utf-8")
            obs=root/"agent-forward-observations"/"fp123";obs.mkdir(parents=True)
            for i,hour in enumerate((10,12)):
                item={"research_sha256":"fp123","symbol":"BTCUSDT",
                      "candle_time_utc":f"2026-10-25T{hour:02d}:00:00Z"}
                (obs/f"{i}.json").write_text(json.dumps(item),encoding="utf-8")
            result=diagnose(td)
            self.assertEqual(result["status"],"gaps_found")
            self.assertEqual(result["gaps"][0]["expected_next_utc"],"2026-10-25T11:00:00+00:00")
            self.assertFalse(result["live_trading_authorized"])
            self.assertEqual(len(list(obs.glob("*.json"))),2)

    def test_empty_state_does_not_claim_complete_history(self):
        with tempfile.TemporaryDirectory() as td:
            result=diagnose(td)
            self.assertEqual(result["status"],"not_started")
            self.assertEqual(result["checked"],0)

if __name__=="__main__":
    unittest.main()
