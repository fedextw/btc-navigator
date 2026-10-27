import hashlib
import json
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
from agent_forward_observation import review_frozen_candidate

class ForwardObservationTests(unittest.TestCase):
    def test_new_only_paper_evidence_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            folder=root/"agent-frozen-paper-candidates"
            folder.mkdir()
            cutoff=datetime(2026,1,5,tzinfo=timezone.utc)
            record={"schema":"bc-frozen-paper-candidate-v1","symbol":"BTCUSDT",
                    "interval":"1h","strategy":"breakout_20",
                    "historical_cutoff_utc":cutoff.isoformat(),
                    "paper_only":True,"automatic_promotion_authorized":False,
                    "live_trading_authorized":False}
            raw=json.dumps(record).encode()
            path=folder/(hashlib.sha256(raw).hexdigest()+".json")
            path.write_bytes(raw)
            base=datetime(2026,1,1,tzinfo=timezone.utc)
            rows=[]
            for i in range(400):
                now=base+timedelta(hours=i)
                p=100+i*0.05
                rows.append((now.isoformat(),p,p+1,p-1,p+0.02,50))
            with patch("agent_forward_observation.history_from_database",return_value=rows):
                result=review_frozen_candidate(root,path)
            self.assertEqual(result["symbol"],"BTCUSDT")
            self.assertIn(result["review"]["status"],
                          ("continue_paper_observation","review_strategy_deterioration"))
            self.assertFalse(result["live_trading_authorized"])
            path.write_bytes(raw+b"x")
            with self.assertRaises(ValueError):
                review_frozen_candidate(root,path)
    def test_no_fresh_data_is_waiting(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); folder=root/"agent-frozen-paper-candidates";folder.mkdir()
            record={"schema":"bc-frozen-paper-candidate-v1","symbol":"BTCUSDT",
                    "interval":"1h","strategy":"trend_10_50",
                    "historical_cutoff_utc":"2026-01-20T00:00:00+00:00",
                    "paper_only":True,"automatic_promotion_authorized":False,
                    "live_trading_authorized":False}
            raw=json.dumps(record).encode()
            path=folder/(hashlib.sha256(raw).hexdigest()+".json");path.write_bytes(raw)
            start=datetime(2026,1,1,tzinfo=timezone.utc)
            rows=[((start+timedelta(hours=i)).isoformat(),100,101,99,100,5) for i in range(300)]
            with patch("agent_forward_observation.history_from_database",return_value=rows):
                self.assertEqual(review_frozen_candidate(root,path)["status"],"waiting_new_closed_candles")

if __name__=="__main__":
    unittest.main()
