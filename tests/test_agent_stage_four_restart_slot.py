import json
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
from agent_stage_four_supervisor import supervise
from agent_stage_four_ui_status import load_openai_status

class CompletedSlotRestartTests(unittest.TestCase):
    def test_same_utc_slot_restart_never_calls_model(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"stage4-universe-cursor.json").write_text(json.dumps({
                "schema":"agent-stage4-universe-cursor-v1",
                "slot":"20261028T12Z","status":"completed",
                "live_trading_authorized":False}),encoding="utf-8")
            calls=[]
            def fake(*a,**k):
                calls.append(1)
                return {"status":"completed"}
            result=supervise(root,max_batches=2,hours=6,runner=fake,
                clock=lambda:datetime(2026,10,28,13,tzinfo=timezone.utc))
            self.assertEqual(calls,[])
            self.assertEqual(result["attempted_slots"][0]["status"],"already_processed")
            self.assertEqual(load_openai_status(Path(d).parent)["state"] if False else
                             json.loads((root/"supervisor-status.json").read_text())["phase"],
                             "completed")
if __name__=="__main__":
    unittest.main()
