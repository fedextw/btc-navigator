import json
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from agent_stage_four_supervisor import supervise

class PersistedNextSlotSafetyTests(unittest.TestCase):
    def test_external_completed_slot_is_not_paid_again(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            now=[datetime(2026,10,28,12,tzinfo=timezone.utc)]
            invoked=[]
            def work(state,**kw):
                invoked.append(kw["slot"])
                return {"status":"completed","paper_only":True,"live_trading_authorized":False}
            def next_slot(seconds):
                now[0]+=timedelta(seconds=seconds)
                slot=f"{now[0].year:04d}{now[0].month:02d}{now[0].day:02d}T{now[0].hour:02d}Z"
                (root/"stage4-universe-cursor.json").write_text(json.dumps({
                    "schema":"agent-stage4-universe-cursor-v1","status":"completed",
                    "slot":slot,"live_trading_authorized":False
                }),encoding="utf-8")
            result=supervise(root,max_batches=2,runner=work,
                clock=lambda:now[0],sleep=next_slot)
            self.assertEqual(len(invoked),1)
            self.assertEqual([x["status"] for x in result["attempted_slots"]],
                             ["completed","already_processed"])
            self.assertFalse(result["live_trading_authorized"])

if __name__=="__main__":
    unittest.main()
