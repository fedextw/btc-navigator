import json
import tempfile
import unittest
from pathlib import Path
from agent_stage_four_supervisor import supervise
from agent_stage_four_ui_status import load_openai_status

class PersistedCursorPreflightTests(unittest.TestCase):
    def test_reserved_rotation_blocks_paid_supervisor_before_model_calls(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"stage4-universe-cursor.json").write_text(json.dumps({
                "schema":"agent-stage4-universe-cursor-v1",
                "status":"reserved","live_trading_authorized":False
            }),encoding="utf-8")
            calls=[]
            def fake(*args,**kwargs):
                calls.append(1)
                return {"status":"completed"}
            with self.assertRaisesRegex(ValueError,"requires manual review"):
                supervise(root,max_batches=1,runner=fake)
            self.assertEqual(calls,[])
            self.assertEqual(load_openai_status(root.parent)["state"] if False else
                             __import__("json").loads((root/"supervisor-status.json").read_text())["phase"],
                             "requires_manual_review")

if __name__=="__main__":
    unittest.main()
