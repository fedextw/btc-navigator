import json
import tempfile
import unittest
from pathlib import Path
from agent_bc_diagnostic import inspect

class BCDiagnosticTests(unittest.TestCase):
    def test_missing_state_is_read_only(self):
        with tempfile.TemporaryDirectory() as t:
            state=Path(t)/"state"
            report=inspect(state,port=65534)
            self.assertFalse(report["state_directory_exists"])
            self.assertEqual(report["agent_status"],"missing")
            self.assertFalse(state.exists())

    def test_status_read_and_never_authorize_trading(self):
        with tempfile.TemporaryDirectory() as t:
            state=Path(t)/"state"
            folder=state/"agent-status";folder.mkdir(parents=True)
            (folder/"latest.json").write_text(json.dumps({
                "phase":"completed","paper_only":True,
                "live_trading_authorized":False,
                "finished_at":"2026-10-25T00:00:00+00:00"
            }),encoding="utf-8")
            result=inspect(state,port=65534)
            self.assertEqual(result["agent_status"],"completed")
            self.assertTrue(result["agent_paper_only"])
            self.assertFalse(result["live_trading_authorized"])
            self.assertFalse((state/"scanner.log").exists())

if __name__=="__main__":
    unittest.main()
