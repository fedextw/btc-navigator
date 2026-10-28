"""Stage-four integration acceptance; real local state, mocked remote services.

Acceptance is deliberately not a claim about provider uptime, forward profitability
or unattended indefinite operation.
"""
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from agent_stage_four_rotation import run_rotation
from agent_stage_four_checkpoint import run_checkpointed
from agent_stage_four_integrated_audit import audit_delivery
from agent_stage_four_supervisor import supervise
from agent_stage_four_ui_status import load_openai_status


class Exchange:
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,n):
        return json.dumps({"symbols":[{
            "symbol":"BTCUSDT","quoteAsset":"USDT","marginAsset":"USDT",
            "contractType":"PERPETUAL","status":"TRADING"
        }]}).encode()


class StageFourReleaseAcceptance(unittest.TestCase):
    def test_supervised_research_persists_verifiable_report_and_dashboard(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            state=root/"stage4-openai"
            research_calls=[]
            def research(work, prior, *, symbol, interval, count, model):
                research_calls.append((symbol,prior))
                self.assertIsNone(prior)
                report={"schema":"agent-orchestrator-v1",
                        "paper_only":True,"live_trading_authorized":False,
                        "dataset_latest_utc":"2026-10-01T00:00:00+00:00",
                        "candidate_count":0,"candidates":[],"selected":None}
                raw=json.dumps(report,sort_keys=True).encode()
                directory=Path(work)/"reports"
                directory.mkdir(parents=True)
                target=directory/(hashlib.sha256(raw).hexdigest()+".json")
                target.write_bytes(raw)
                return {"paper_only":True,"live_trading_authorized":False,
                        "report_path":str(target)}
            def checkpoint(work, prior, **kwargs):
                return run_checkpointed(work,prior,runner=research,**kwargs)
            def rotation(work, **kwargs):
                return run_rotation(work,fetch=lambda *a,**kw:Exchange(),
                                    runner=checkpoint,**kwargs)
            result=supervise(state,max_batches=1,runner=rotation,
                clock=lambda:datetime(2026,10,28,12,tzinfo=timezone.utc))
            self.assertEqual(result["attempted_slots"][0]["status"],"completed")
            self.assertEqual(len(research_calls),1)
            self.assertTrue(audit_delivery(state)["engineering_evidence_valid"])
            self.assertEqual(load_openai_status(root)["state"],"completed")
            repeat=supervise(state,max_batches=1,runner=rotation,
                clock=lambda:datetime(2026,10,28,12,tzinfo=timezone.utc))
            self.assertEqual(repeat["attempted_slots"][0]["status"],"already_processed")
            self.assertEqual(len(research_calls),1)
            self.assertFalse(result["live_trading_authorized"])


if __name__=="__main__":
    unittest.main()
