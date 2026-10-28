import tempfile
import unittest
from pathlib import Path
from agent_stage_four_multimarket import run_batch

class MultiMarketStage4Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
    def test_unique_market_isolation_and_parent_mapping(self):
        calls=[]
        def fake(state,prior,**kw):
            calls.append((Path(state),prior,kw))
            return {"status":"completed","live_trading_authorized":False}
        out=run_batch(self.root,symbols=("BTCUSDT","ETHUSDT"),
                      seed_reports={"BTCUSDT":"btc.json","ETHUSDT":"eth.json"},
                      slot="20261028T00Z",runner=fake)
        self.assertEqual([x[1] for x in calls],["btc.json","eth.json"])
        self.assertNotEqual(calls[0][0],calls[1][0])
        self.assertEqual(out["items"][0]["status"],"completed")
        self.assertFalse(out["live_trading_authorized"])
    def test_failure_is_isolated_per_symbol(self):
        def fake(state,prior,**kw):
            if kw["symbol"]=="BTCUSDT":
                raise RuntimeError("ambiguous model outcome")
            return {"status":"completed"}
        out=run_batch(self.root,symbols=("BTCUSDT","ETHUSDT"),
                      seed_reports={"BTCUSDT":"btc.json","ETHUSDT":"eth.json"},
                      slot="20261028T00Z",runner=fake)
        self.assertEqual([x["status"] for x in out["items"]],
                         ["requires_manual_review","completed"])
    def test_missing_seed_rejected_before_model_calls(self):
        calls=[]
        with self.assertRaisesRegex(ValueError,"seed"):
            run_batch(self.root,symbols=("BTCUSDT","ETHUSDT"),
                      seed_reports={"BTCUSDT":"btc.json"},
                      slot="20261028T00Z",runner=lambda *a,**kw:calls.append(True))
        self.assertFalse(calls)
    def test_duplicate_symbol_rejected(self):
        with self.assertRaisesRegex(ValueError,"unique"):
            run_batch(self.root,symbols=("BTCUSDT","BTCUSDT"),
                      seed_reports={"BTCUSDT":"btc.json"},slot="20261028T00Z")
if __name__=="__main__":
    unittest.main()
