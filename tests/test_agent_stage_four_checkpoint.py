import json
import tempfile
import unittest
from pathlib import Path
from agent_stage_four_checkpoint import run_checkpointed

class Stage4CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
    def test_reservation_and_duplicate_slot_are_safe(self):
        calls=[]
        def runner(out,prior,**kw):
            calls.append((out,prior,kw))
            return {"report_path":"immutable.json","paper_only":True,
                    "live_trading_authorized":False}
        a=run_checkpointed(self.root,"prior.json",slot="hour-001",runner=runner)
        b=run_checkpointed(self.root,"prior.json",slot="hour-001",runner=runner)
        self.assertEqual(a["status"],"completed")
        self.assertEqual(b["status"],"already_completed")
        self.assertEqual(len(calls),1)
        self.assertFalse(b["live_trading_authorized"])
        checkpoint=json.loads((self.root/"stage4-checkpoint.json").read_text(encoding="utf-8"))
        self.assertEqual(checkpoint["status"],"completed")
    def test_failed_run_never_retries_billable_call(self):
        calls=[]
        def broken(*args,**kwargs):
            calls.append(True)
            raise RuntimeError("Provider timed out after request")
        with self.assertRaises(RuntimeError):
            run_checkpointed(self.root,"prior.json",slot="hour-002",runner=broken)
        result=run_checkpointed(self.root,"prior.json",slot="hour-002",runner=broken)
        self.assertEqual(result["status"],"requires_manual_review")
        self.assertEqual(len(calls),1)
        other=run_checkpointed(self.root,"prior.json",slot="hour-003",runner=broken)
        self.assertEqual(other["status"],"requires_manual_review")
        self.assertEqual(len(calls),1)
    def test_unsafe_result_does_not_complete(self):
        runner=lambda *a,**kw:{"report_path":"x","paper_only":False,"live_trading_authorized":True}
        with self.assertRaisesRegex(ValueError,"Unsafe"):
            run_checkpointed(self.root,"prior.json",slot="hour-004",runner=runner)
        state=json.loads((self.root/"stage4-checkpoint.json").read_text(encoding="utf-8"))
        self.assertEqual(state["status"],"reserved")
    def test_next_slot_uses_completed_report_not_original_seed(self):
        one=self.root/"first.json"
        two=self.root/"second.json"
        one.write_text("first report",encoding="utf-8")
        two.write_text("second report",encoding="utf-8")
        parents=[]
        def runner(out,parent,**kwargs):
            parents.append(str(parent))
            return {"report_path":str(one if len(parents)==1 else two),
                    "paper_only":True,"live_trading_authorized":False}
        run_checkpointed(self.root,"initial.json",slot="hour-001",runner=runner)
        run_checkpointed(self.root,"initial.json",slot="hour-002",runner=runner)
        self.assertEqual(parents,["initial.json",str(one)])
    def test_next_slot_refuses_missing_prior_evidence(self):
        prior=self.root/"vanished.json"
        prior.write_text("evidence",encoding="utf-8")
        def runner(*args,**kw):
            return {"report_path":str(prior),"paper_only":True,
                    "live_trading_authorized":False}
        run_checkpointed(self.root,"initial.json",slot="hour-001",runner=runner)
        prior.unlink()
        with self.assertRaisesRegex(ValueError,"report missing"):
            run_checkpointed(self.root,"initial.json",slot="hour-002",runner=runner)
    def test_invalid_slot_rejected_without_state(self):
        with self.assertRaises(ValueError):
            run_checkpointed(self.root,"prior.json",slot="../escape")
        self.assertFalse((self.root/"stage4-checkpoint.json").exists())
if __name__=="__main__":
    unittest.main()
