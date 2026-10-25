import json
import tempfile
import unittest
from pathlib import Path
from agent_stage5_cycle import run_rotation

class RotationResumeTests(unittest.TestCase):
    def test_resume_checkpoint_advances_after_completed_cycles(self):
        with tempfile.TemporaryDirectory() as td:
            seen=[]
            def runner(state,*,batch_number):
                seen.append(batch_number)
                return {"schema":"agent-stage5-cycle-v1","research":{},
                        "automatic_promotion_authorized":False,
                        "live_trading_authorized":False}
            run_rotation(td,rounds=2,cycle_runner=runner,resume=True)
            self.assertEqual(seen,[0,1])
            run_rotation(td,rounds=2,cycle_runner=runner,resume=True)
            self.assertEqual(seen,[0,1,2,3])
            data=json.loads((Path(td)/"agent-stage5-rotation-progress.json").read_text(encoding="utf-8"))
            self.assertEqual(data["next_batch"],4)
    def test_no_ready_data_does_not_advance_checkpoint(self):
        with tempfile.TemporaryDirectory() as td:
            result=run_rotation(td,rounds=3,resume=True,cycle_runner=lambda state,*,batch_number:{
                "schema":"agent-stage5-cycle-v1","status":"waiting_for_research_ready_symbols",
                "automatic_promotion_authorized":False,"live_trading_authorized":False})
            self.assertEqual(result["completed_cycles"],0)
            self.assertFalse((Path(td)/"agent-stage5-rotation-progress.json").exists())
    def test_unsafe_result_never_writes_checkpoint(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                run_rotation(td,resume=True,cycle_runner=lambda state,*,batch_number:{
                    "schema":"agent-stage5-cycle-v1",
                    "automatic_promotion_authorized":True,"live_trading_authorized":False})
            self.assertFalse((Path(td)/"agent-stage5-rotation-progress.json").exists())
if __name__=="__main__":
    unittest.main()
