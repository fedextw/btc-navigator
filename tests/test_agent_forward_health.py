import tempfile
import unittest
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
            self.assertEqual(len(list((Path(td)/"agent-forward-health").glob("*.json"))),2)

if __name__=="__main__":
    unittest.main()
