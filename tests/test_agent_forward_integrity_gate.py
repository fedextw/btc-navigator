import json
import tempfile
import unittest
from pathlib import Path
from agent_forward_pipeline import run_once

class ForwardIntegrityGateTests(unittest.TestCase):
    def test_corrupt_evidence_blocks_performance_claim(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            enrollment=root/"agent-forward"
            enrollment.mkdir()
            (enrollment/"one.json").write_text(json.dumps({
                "schema":"agent-forward-enrollment-v1",
                "live_trading_authorized":False,
                "research_sha256":"test123",
                "symbol":"BTCUSDT","strategy":"trend_8_30"
            }),encoding="utf-8")
            observations=root/"agent-forward-observations"/"test123"
            observations.mkdir(parents=True)
            for idx,hour in enumerate((10,12)):
                (observations/f"{idx}.json").write_text(json.dumps({
                    "research_sha256":"test123","symbol":"BTCUSDT",
                    "candle_time_utc":f"2026-10-25T{hour:02d}:00:00Z"
                }),encoding="utf-8")
            outcome=run_once(td,now="2026-10-25T14:00:00Z")
            self.assertEqual(outcome["status"],"blocked_data_gap")
            self.assertIsNone(outcome["dashboard"])
            self.assertEqual(outcome["data_integrity"]["status"],"gaps_found")
            self.assertFalse(outcome["live_trading_authorized"])

if __name__=="__main__":
    unittest.main()
