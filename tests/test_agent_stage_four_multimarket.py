import tempfile
import unittest
from pathlib import Path
from agent_stage_four_multimarket import run_batch,run_discovered_batch
from unittest.mock import patch

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
    def test_discovery_uses_only_active_markets_with_own_seed(self):
        calls=[]
        def fake(*args,**kwargs):
            calls.append(kwargs["symbol"])
            return {"status":"completed"}
        universe={"symbols":["BTCUSDT","ETHUSDT","SOLUSDT"],"eligible_total":3}
        with patch("agent_stage_four_multimarket.discover",return_value=universe):
            result=run_discovered_batch(self.root,seed_reports={"BTCUSDT":"btc.json",
                          "SOLUSDT":"sol.json"},slot="20261028T00Z",runner=fake)
        self.assertEqual(calls,["BTCUSDT","SOLUSDT"])
        self.assertEqual(len(result["items"]),2)
        self.assertFalse(result["live_trading_authorized"])
    def test_unseeded_active_contracts_do_not_borrow_other_reports(self):
        with patch("agent_stage_four_multimarket.discover",
                   return_value={"symbols":["ETHUSDT"],"eligible_total":1}):
            result=run_discovered_batch(self.root,seed_reports={"BTCUSDT":"btc.json"},
                                        slot="20261028T00Z")
        self.assertEqual(result["status"],"no_seeded_active_contracts")
        self.assertEqual(result["items"],[])
    def test_duplicate_symbol_rejected(self):
        with self.assertRaisesRegex(ValueError,"unique"):
            run_batch(self.root,symbols=("BTCUSDT","BTCUSDT"),
                      seed_reports={"BTCUSDT":"btc.json"},slot="20261028T00Z")
if __name__=="__main__":
    unittest.main()
