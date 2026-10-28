import json
import tempfile
import unittest
from pathlib import Path
from agent_stage_four_readiness import check_batch_readiness
from agent_stage_four_rotation import run_rotation

class StageFourInterruptedMarketAcceptanceTests(unittest.TestCase):
    def test_interrupted_market_returns_safe_manual_review_without_model_calls(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            checkpoint=root/"markets"/"BTCUSDT"/"1h"/"stage4-checkpoint.json"
            checkpoint.parent.mkdir(parents=True)
            checkpoint.write_text(json.dumps({"schema":"agent-stage4-checkpoint-v1",
                "status":"reserved","live_trading_authorized":False}),encoding="utf-8")
            readiness=check_batch_readiness(root,["BTCUSDT"])
            self.assertEqual(readiness["status"],"requires_manual_review")
            self.assertIs(readiness["paper_only"],True)
            self.assertIs(readiness["live_trading_authorized"],False)
            class Exchange:
                def __enter__(self):return self
                def __exit__(self,*args):return False
                def read(self,n):
                    return json.dumps({"symbols":[{"symbol":"BTCUSDT",
                        "quoteAsset":"USDT","marginAsset":"USDT",
                        "contractType":"PERPETUAL","status":"TRADING"}]}).encode()
            calls=[]
            outcome=run_rotation(root,slot="20261029T00Z",
                fetch=lambda *a,**kw:Exchange(),
                runner=lambda *a,**kw:calls.append(1))
            self.assertEqual(outcome["status"],"requires_manual_review")
            self.assertIs(outcome["paper_only"],True)
            self.assertIs(outcome["live_trading_authorized"],False)
            self.assertEqual(calls,[])

if __name__=="__main__":
    unittest.main()
