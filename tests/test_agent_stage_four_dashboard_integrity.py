import json
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from agent_stage_four_ui_status import load_openai_status

class PaidResearchDashboardIntegrityTests(unittest.TestCase):
    def verify(self, **changes):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"stage4-openai"/"supervisor-status.json"
            path.parent.mkdir()
            record={"schema":"agent-stage4-supervisor-status-v1",
                    "paper_only":True,"live_trading_authorized":False,
                    "phase":"running",
                    "updated_at_utc":datetime.now(timezone.utc).isoformat(),
                    "completed_batches":0,"max_model_calls_authorized":10}
            record.update(changes)
            path.write_text(json.dumps(record),encoding="utf-8")
            return load_openai_status(d)["state"]
    def test_valid_status(self):
        self.assertEqual(self.verify(),"running")
    def test_reject_future_clock_and_impossible_billing(self):
        self.assertEqual(self.verify(updated_at_utc=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()),"invalid")
        for options in ({"completed_batches":2},{"completed_batches":-1},
                        {"completed_batches":True},{"max_model_calls_authorized":241},
                        {"max_model_calls_authorized":-1}):
            with self.subTest(options=options):
                self.assertEqual(self.verify(**options),"invalid")

if __name__=="__main__":
    unittest.main()
