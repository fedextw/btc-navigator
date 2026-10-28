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
    def test_invalid_slot_rejected_without_state(self):
        with self.assertRaises(ValueError):
            run_checkpointed(self.root,"prior.json",slot="../escape")
        self.assertFalse((self.root/"stage4-checkpoint.json").exists())
if __name__=="__main__":
    unittest.main()
