import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from agent_stage_four_supervisor import supervise
from agent_stage_four_ui_status import load_openai_status

class RepeatedSlotGuardTests(unittest.TestCase):
    def test_repeat_slot_stops_without_second_model_call_and_marks_error(self):
        with tempfile.TemporaryDirectory() as d:
            count=[]
            clock=lambda:datetime(2026,10,28,12,tzinfo=timezone.utc)
            def fake(*args,**kwargs):
                count.append(1)
                return {"status":"completed"}
            with self.assertRaisesRegex(ValueError,"UTC slot repeated"):
                supervise(Path(d)/"stage4-openai",max_batches=2,
                          runner=fake,clock=clock,sleep=lambda seconds:None)
            self.assertEqual(len(count),1)
            self.assertEqual(load_openai_status(d)["state"],"error")

if __name__=="__main__":
    unittest.main()
