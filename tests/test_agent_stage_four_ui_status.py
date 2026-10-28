import json
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from agent_stage_four_ui_status import load_openai_status
from agent_stage_four_supervisor import supervise

class StageFourStatusTests(unittest.TestCase):
    def test_unstarted_is_not_claimed_running(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(load_openai_status(d)["state"],"not_started")
    def test_successful_batch_updates_read_only_dashboard(self):
        with tempfile.TemporaryDirectory() as d:
            seen=[]
            def fake(state,**kw):
                seen.append(kw["slot"])
                return {"status":"completed"}
            result=supervise(Path(d)/"stage4-openai",max_batches=1,runner=fake,
                clock=lambda:datetime(2026,10,28,12,tzinfo=timezone.utc))
            status=load_openai_status(d)
            self.assertEqual(status["state"],"completed")
            self.assertEqual(status["completed_batches"],1)
            self.assertEqual(status["max_model_calls_authorized"],10)
            self.assertFalse(result["live_trading_authorized"])
    def test_manual_review_persists_and_does_not_rerun(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/"stage4-openai"
            supervise(state,max_batches=1,runner=lambda *a,**kw:{"status":"requires_manual_review"},
                clock=lambda:datetime(2026,10,28,12,tzinfo=timezone.utc))
            self.assertEqual(load_openai_status(d)["state"],"requires_manual_review")
    def test_wait_is_not_misrepresented_as_completed(self):
        with tempfile.TemporaryDirectory() as d:
            supervise(Path(d)/"stage4-openai",max_batches=1,
                runner=lambda *a,**kw:{"status":"waiting_for_fresh_data"},
                clock=lambda:datetime(2026,10,28,12,tzinfo=timezone.utc))
            self.assertEqual(load_openai_status(d)["state"],"waiting_for_fresh_data")
    def test_old_running_record_is_not_claimed_active(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"stage4-openai"/"supervisor-status.json"
            path.parent.mkdir()
            path.write_text(json.dumps({
                "schema":"agent-stage4-supervisor-status-v1",
                "phase":"running","paper_only":True,
                "live_trading_authorized":False,
                "updated_at_utc":(datetime.now(timezone.utc)-timedelta(hours=3)).isoformat()
            }),encoding="utf-8")
            self.assertEqual(load_openai_status(d)["state"],"stale")
    def test_corrupted_status_is_not_displayed_as_success(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"stage4-openai"/"supervisor-status.json"
            path.parent.mkdir()
            path.write_text('{"schema":"unexpected"}',encoding="utf-8")
            self.assertEqual(load_openai_status(d)["state"],"invalid")
if __name__=="__main__":
    unittest.main()
