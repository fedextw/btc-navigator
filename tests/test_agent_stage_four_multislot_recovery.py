import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from agent_stage_four_supervisor import supervise
from agent_stage_four_ui_status import load_openai_status

class MultiSlotRecoveryAcceptance(unittest.TestCase):
    def test_wait_for_fresh_data_then_complete_next_slot_no_unapproved_retry(self):
        with tempfile.TemporaryDirectory() as d:
            now=[datetime(2026,10,28,12,tzinfo=timezone.utc)]
            calls=[]
            def research(*args,**kwargs):
                calls.append(kwargs["slot"])
                status="waiting_for_fresh_data" if len(calls)==1 else "completed"
                return {"status":status,"paper_only":True,"live_trading_authorized":False}
            def advance(seconds):
                self.assertGreater(seconds,0)
                now[0]+=timedelta(seconds=seconds)
            result=supervise(Path(d)/"stage4-openai",max_batches=2,
                runner=research,clock=lambda:now[0],sleep=advance)
            self.assertEqual(len(calls),2)
            self.assertNotEqual(calls[0],calls[1])
            self.assertEqual([x["status"] for x in result["attempted_slots"]],
                             ["waiting_for_fresh_data","completed"])
            self.assertEqual(result["max_model_calls_authorized"],20)
            self.assertEqual(load_openai_status(d)["state"],"completed")
            self.assertFalse(result["live_trading_authorized"])

if __name__=="__main__":
    unittest.main()
