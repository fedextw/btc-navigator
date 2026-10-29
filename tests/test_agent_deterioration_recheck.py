import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from agent_forward_batch import review_frozen_batch

class DeteriorationRecheckTests(unittest.TestCase):
    def test_deterioration_emits_research_only_recheck(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)/"agent-frozen-paper-candidates"
            folder.mkdir()
            record={"schema":"bc-frozen-paper-candidate-v1",
                    "symbol":"BTCUSDT","interval":"1h","strategy":"trend_10_50",
                    "paper_only":True,"automatic_promotion_authorized":False,
                    "live_trading_authorized":False}
            raw=json.dumps(record).encode("utf-8")
            path=folder/(hashlib.sha256(raw).hexdigest()+".json")
            path.write_bytes(raw)
            fake={"review":{"status":"review_strategy_deterioration"},
                  "live_trading_authorized":False}
            with patch("agent_forward_batch.review_frozen_candidate",return_value=fake):
                result=review_frozen_batch(td)
            request=result["items"][0]["research_recheck"]
            self.assertEqual(request["symbol"],"BTCUSDT")
            self.assertEqual(request["interval"],"1h")
            self.assertFalse(request["automatic_promotion_authorized"])
            self.assertFalse(request["live_trading_authorized"])

    def test_no_recheck_for_waiting_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)/"agent-frozen-paper-candidates"
            folder.mkdir()
            (folder/("a"*64+".json")).write_text("{}",encoding="utf-8")
            with patch("agent_forward_batch.review_frozen_candidate",
                       return_value={"status":"waiting_new_paper_trades","live_trading_authorized":False}):
                result=review_frozen_batch(td)
            self.assertNotIn("research_recheck",result["items"][0])

if __name__=="__main__":
    unittest.main()
