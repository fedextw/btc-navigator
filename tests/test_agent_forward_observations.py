import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from agent_forward_observations import record_candle

class ForwardObservationsTests(unittest.TestCase):
    def setUp(self):
        self.enrollment={"schema":"agent-forward-enrollment-v1","live_trading_authorized":False,
                         "research_sha256":"abc123","symbol":"BTCUSDT","strategy":"trend_8_30",
                         "data_cutoff_utc":"2026-10-23T00:00:00Z",
                         "enrolled_at_utc":"2026-10-25T00:00:00Z"}
        self.bar={"time":"2026-10-25T01:00:00Z","close_time":"2026-10-25T01:59:59Z",
                  "open":100,"high":110,"low":95,"close":105,"volume":10}

    def test_append_only_and_duplicate_does_not_expand(self):
        with tempfile.TemporaryDirectory() as td:
            p=record_candle(self.enrollment,self.bar,td,observed_at="2026-10-25T02:01:00Z")
            self.assertEqual(p,record_candle(self.enrollment,self.bar,td,observed_at="2026-10-25T02:02:00Z"))
            self.assertEqual(len(list(Path(td).glob("*.json"))),1)
            self.assertEqual(json.loads(p.read_text())["status"],"observed_not_traded")

    def test_never_accepts_pre_enrollment_or_open_candle(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                record_candle(self.enrollment,{**self.bar,"time":"2026-10-24T01:00:00Z"},td,observed_at="2026-10-25T02:01:00Z")
            with self.assertRaises(ValueError):
                record_candle(self.enrollment,self.bar,td,observed_at="2026-10-25T01:30:00Z")
            self.assertEqual(list(Path(td).iterdir()),[])

    def test_conflicting_market_data_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            record_candle(self.enrollment,self.bar,td,observed_at="2026-10-25T02:01:00Z")
            with self.assertRaises(RuntimeError):
                record_candle(self.enrollment,{**self.bar,"close":106},td,observed_at="2026-10-25T02:02:00Z")

if __name__=="__main__":
    unittest.main()
