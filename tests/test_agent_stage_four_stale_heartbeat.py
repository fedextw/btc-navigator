import json
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from agent_stage_four_ui_status import load_openai_status

class StaleSupervisorHeartbeatTests(unittest.TestCase):
    def test_active_and_waiting_states_must_have_fresh_heartbeat(self):
        for phase in ("running","waiting_for_next_slot","waiting_for_fresh_data"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as d:
                folder=Path(d)/"stage4-openai"
                folder.mkdir()
                (folder/"supervisor-status.json").write_text(json.dumps({
                    "schema":"agent-stage4-supervisor-status-v1",
                    "phase":phase,
                    "updated_at_utc":(datetime.now(timezone.utc)-timedelta(hours=3)).isoformat(),
                    "paper_only":True,"live_trading_authorized":False
                }),encoding="utf-8")
                self.assertEqual(load_openai_status(d)["state"],"stale")
    def test_completed_history_does_not_become_stale(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)/"stage4-openai"
            folder.mkdir()
            (folder/"supervisor-status.json").write_text(json.dumps({
                "schema":"agent-stage4-supervisor-status-v1",
                "phase":"completed",
                "updated_at_utc":(datetime.now(timezone.utc)-timedelta(days=3)).isoformat(),
                "paper_only":True,"live_trading_authorized":False
            }),encoding="utf-8")
            self.assertEqual(load_openai_status(d)["state"],"completed")
if __name__=="__main__":
    unittest.main()
