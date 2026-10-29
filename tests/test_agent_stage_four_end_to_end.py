"""Offline end-to-end rotation -> per-market checkpoints -> evidence audit.

Exercise real orchestration and real persistence, mocking only the external
Binance HTTP response and research model/evaluation output.
"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from agent_stage_four_checkpoint import run_checkpointed
from agent_stage_four_rotation import run_rotation
from agent_stage_four_integrated_audit import audit_delivery

class Response:
    def __init__(self,symbols):
        self.data=json.dumps({"symbols":[
            {"symbol":s,"quoteAsset":"USDT","marginAsset":"USDT",
             "contractType":"PERPETUAL","status":"TRADING"}
            for s in symbols]}).encode()
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,size):return self.data[:size]

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.parents={}
        self.calls=[]
    def fetch(self,*args,**kwargs):
        return Response(["BTCUSDT","ETHUSDT"])
    def research(self,out,prior,*,symbol,interval,count,model):
        self.calls.append(symbol)
        self.parents.setdefault(symbol,[]).append(prior)
        data={"schema":"agent-orchestrator-v1","paper_only":True,
              "live_trading_authorized":False,"dataset_latest_utc":"2020-01-01T00:00:00+00:00","candidate_count":1,
              "candidates":[{"status":"rejected"}],"selected":None}
        blob=json.dumps(data,sort_keys=True).encode()
        output=Path(out)/"reports"
        output.mkdir(parents=True,exist_ok=True)
        path=output/(hashlib.sha256(blob).hexdigest()+".json")
        path.write_bytes(blob)
        return {"paper_only":True,"live_trading_authorized":False,
                "report_path":str(path)}
    def checkpoint_runner(self,out,prior,**kwargs):
        return run_checkpointed(out,prior,runner=self.research,**kwargs)
    def test_full_rotation_evidence_and_duplicate_slot(self):
        first=run_rotation(self.root,slot="SLOT01",fetch=self.fetch,
                           runner=self.checkpoint_runner)
        self.assertEqual(first["status"],"completed")
        self.assertEqual(self.calls,["BTCUSDT","ETHUSDT"])
        evidence=audit_delivery(self.root)
        self.assertTrue(evidence["engineering_evidence_valid"])
        self.assertEqual(evidence["reports_verified"],2)
        self.assertFalse(evidence["forward_performance_validated"])
        repeated=run_rotation(self.root,slot="SLOT01",fetch=self.fetch,
                              runner=self.checkpoint_runner)
        self.assertEqual(repeated["status"],"already_processed")
        self.assertEqual(len(self.calls),2)
    def test_previous_generation_is_reused_per_market(self):
        run_rotation(self.root,slot="SLOT01",fetch=self.fetch,
                     runner=self.checkpoint_runner)
        second=run_rotation(self.root,slot="SLOT02",fetch=self.fetch,
                            runner=self.checkpoint_runner)
        self.assertEqual(second["status"],"completed")
        self.assertIsNone(self.parents["BTCUSDT"][0])
        self.assertIsNone(self.parents["ETHUSDT"][0])
        self.assertTrue(Path(self.parents["BTCUSDT"][1]).is_file())
        self.assertTrue(Path(self.parents["ETHUSDT"][1]).is_file())
        self.assertIn("BTCUSDT",self.parents["BTCUSDT"][1])
        self.assertIn("ETHUSDT",self.parents["ETHUSDT"][1])
        self.assertTrue(audit_delivery(self.root)["engineering_evidence_valid"])
    def test_one_failed_market_blocks_rotation_audit(self):
        def mixed(out,prior,**kwargs):
            if kwargs["symbol"]=="ETHUSDT":
                raise RuntimeError("ambiguous model timeout")
            return self.checkpoint_runner(out,prior,**kwargs)
        result=run_rotation(self.root,slot="SLOT01",fetch=self.fetch,runner=mixed)
        self.assertEqual(result["status"],"requires_manual_review")
        self.assertFalse(audit_delivery(self.root)["engineering_evidence_valid"])
if __name__=="__main__":
    unittest.main()
