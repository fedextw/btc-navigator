import json
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from agent_stage_four_supervisor import supervise

class AuthorizedResumeAfterCompletedSlotTests(unittest.TestCase):
    def test_skip_completed_current_slot_then_run_future_slot_under_existing_budget(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)
            now=[datetime(2026,10,28,12,tzinfo=timezone.utc)]
            (state/"stage4-universe-cursor.json").write_text(json.dumps({
                "schema":"agent-stage4-universe-cursor-v1","status":"completed",
                "slot":"20261028T12Z","live_trading_authorized":False
            }),encoding="utf-8")
            calls=[]
            def runner(*a,**kw):
                calls.append(kw["slot"])
                return {"status":"completed","paper_only":True,"live_trading_authorized":False}
            def advance(n):now[0]+=timedelta(seconds=n)
            outcome=supervise(state,max_batches=2,runner=runner,
                              clock=lambda:now[0],sleep=advance)
            self.assertEqual(calls,["20261028T18Z"])
            self.assertEqual([x["status"] for x in outcome["attempted_slots"]],
                             ["already_processed","completed"])
            self.assertFalse(outcome["live_trading_authorized"])

if __name__=="__main__":
    unittest.main()
