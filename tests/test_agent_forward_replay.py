import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from agent_forward_replay import replay
from agent_forward_observations import record_candle

class ForwardReplayTests(unittest.TestCase):
    def test_replays_only_new_closed_bars(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            enrollment={"schema":"agent-forward-enrollment-v1","symbol":"BTCUSDT",
                        "strategy":"trend_8_30","research_sha256":"fingerprint",
                        "live_trading_authorized":False,
                        "data_cutoff_utc":"2026-10-20T00:00:00Z",
                        "enrolled_at_utc":"2026-10-25T00:00:00Z"}
            ep=base/"enrollment.json"
            ep.write_text(json.dumps(enrollment),encoding="utf-8")
            rows=base/"rows"
            start=datetime(2026,10,26,tzinfo=timezone.utc)
            for i in range(100):
                at=start+timedelta(hours=i)
                price=100+i*.1
                bar={"time":at.isoformat(),
                     "close_time":(at+timedelta(minutes=59,seconds=59)).isoformat(),
                     "open":price,"high":price+1,"low":price-1,
                     "close":price+.1,"volume":5}
                record_candle(enrollment,bar,rows,observed_at=(at+timedelta(hours=1)).isoformat())
            result=replay(ep,rows)
            self.assertEqual(result["observed_bars"],100)
            self.assertEqual(result["forward_status"],"hypothetical_not_realized")
            self.assertFalse(result["live_trading_authorized"])

    def test_empty_directory_waits(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"enrollment.json"
            p.write_text(json.dumps({"schema":"agent-forward-enrollment-v1",
                "live_trading_authorized":False,"symbol":"BTCUSDT",
                "strategy":"trend_8_30","research_sha256":"fp",
                "enrolled_at_utc":"2026-10-25T00:00:00Z"}),encoding="utf-8")
            self.assertEqual(replay(p,Path(td)/"absent")["status"],"waiting_future_candles")

if __name__=="__main__":
    unittest.main()
