import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from agent_stage_four_supervisor import supervise
from agent_stage_four_ui_status import load_openai_status

class StageFourIdleBetweenSlotsTest(unittest.TestCase):
    def test_data_wait_keeps_waiting_state_during_schedule_pause(self):
        with tempfile.TemporaryDirectory() as d:
            slots=iter([datetime(2026,10,28,12,tzinfo=timezone.utc),
                        datetime(2026,10,28,12,tzinfo=timezone.utc),
                        datetime(2026,10,28,18,tzinfo=timezone.utc)])
            states=[]
            def pause(seconds):
                states.append(load_openai_status(d)["state"])
            supervise(Path(d)/"stage4-openai",max_batches=2,hours=6,
                runner=lambda *args,**kwargs:{"status":"waiting_for_fresh_data"},
                clock=lambda:next(slots),sleep=pause)
            self.assertEqual(states,["waiting_for_fresh_data"])
    def test_idle_status_not_claimed_to_be_model_running(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/"stage4-openai"
            slots=iter([datetime(2026,10,28,12,tzinfo=timezone.utc),
                        datetime(2026,10,28,12,tzinfo=timezone.utc),
                        datetime(2026,10,28,18,tzinfo=timezone.utc)])
            observed=[]
            def pause(seconds):
                observed.append(load_openai_status(d)["state"])
                self.assertGreater(seconds,0)
            outcome=supervise(state,max_batches=2,hours=6,
                runner=lambda *args,**kwargs:{"status":"completed"},
                clock=lambda:next(slots),sleep=pause)
            self.assertEqual(observed,["waiting_for_next_slot"])
            self.assertEqual(load_openai_status(d)["state"],"completed")
            self.assertEqual(len(outcome["attempted_slots"]),2)

if __name__=="__main__":
    unittest.main()
