import json
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
from agent_stage_four_supervisor import supervise

class NoRealTimeWaitInCITests(unittest.TestCase):
    def test_ci_rejects_real_clock_wait_on_completed_restart(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"stage4-universe-cursor.json").write_text(json.dumps({
                "schema":"agent-stage4-universe-cursor-v1",
                "slot":"20261028T12Z","status":"completed",
                "live_trading_authorized":False}),encoding="utf-8")
            called=[]
            with patch.dict("os.environ",{"CI":"true"}):
                with self.assertRaisesRegex(RuntimeError,"virtual clock"):
                    supervise(root,max_batches=2,
                        runner=lambda *a,**k: called.append(1),
                        clock=lambda:datetime(2026,10,28,13,tzinfo=timezone.utc))
            self.assertEqual(called,[])

    def test_ci_rejects_real_wait_after_completed_batch(self):
        with tempfile.TemporaryDirectory() as d:
            called=[]
            with patch.dict("os.environ",{"CI":"true"}):
                with self.assertRaisesRegex(RuntimeError,"virtual clock"):
                    supervise(d,max_batches=2,
                        runner=lambda *a,**k:(called.append(1) or {"status":"completed"}),
                        clock=lambda:datetime(2026,10,28,13,tzinfo=timezone.utc))
            self.assertEqual(called,[1])

if __name__=="__main__":
    unittest.main()
