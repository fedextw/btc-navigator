import tempfile
import unittest
from datetime import datetime,timezone
from unittest.mock import patch
from agent_stage_four_supervisor import supervise

class UTCBoundaryRaceRegressionTests(unittest.TestCase):
    def test_still_same_slot_after_sleep_waits_instead_of_failing(self):
        with tempfile.TemporaryDirectory() as root:
            now=[datetime(2026,10,29,0,0,tzinfo=timezone.utc)]
            calls=[]
            def fake_runner(state,**kw):
                calls.append(kw["slot"])
                return {"status":"completed"}
            def clock():
                return now[0]
            def sleep(seconds):
                # First scheduled wait ended just before next UTC slot.
                if now[0].hour==0 and now[0].minute==0:
                    now[0]=datetime(2026,10,29,5,59,59,tzinfo=timezone.utc)
                else:
                    now[0]=datetime(2026,10,29,6,0,0,tzinfo=timezone.utc)
            with patch.dict("os.environ",{"CI":""}),\
                 patch("agent_stage_four_supervisor.time.sleep",side_effect=sleep),\
                 patch("agent_stage_four_supervisor.time.monotonic",side_effect=[0,21601]):
                result=supervise(root,max_batches=2,runner=fake_runner,clock=clock)
            self.assertEqual(calls,["20261029T00Z","20261029T06Z"])
            self.assertEqual(len(result["attempted_slots"]),2)
if __name__=="__main__":unittest.main()
