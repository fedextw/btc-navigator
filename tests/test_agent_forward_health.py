import tempfile
import unittest
import json
from pathlib import Path
from agent_forward_health import append_status,read_latest
from agent_forward_periodic import run_periodic

class ForwardHealthTests(unittest.TestCase):
    def test_read_last_and_deny_live_authority(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(read_latest(td)["state"],"not_started")
            report={"status":"completed","cycles":[{"status":"completed"}],"live_trading_authorized":False}
            append_status(td,report,stamp="2026-10-25T12:00:00Z")
            self.assertEqual(read_latest(td)["state"],"completed")
            with self.assertRaises(ValueError):
                append_status(td,{"status":"completed","live_trading_authorized":True})
    def test_periodic_run_records_health(self):
        with tempfile.TemporaryDirectory() as td:
            run_periodic(td,interval_seconds=300,cycles=1,
                         runner=lambda _:{"status":"completed"})
            self.assertEqual(read_latest(td)["state"],"completed")
            records=sorted((Path(td)/"agent-forward-health").glob("*.json"))
            self.assertEqual(len(records),2)
            payloads=[json.loads(path.read_text(encoding="utf-8")) for path in records]
            self.assertEqual([p["cycles"] for p in payloads],[1,1])
            self.assertTrue(all(p["status"]=="completed" and p["live_trading_authorized"] is False for p in payloads))

if __name__=="__main__":
    unittest.main()
