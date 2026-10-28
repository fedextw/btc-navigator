import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from agent_stage_four_supervisor import supervise

class OpenAISupervisorTests(unittest.TestCase):
    def test_bounded_execution_is_paper_only(self):
        with tempfile.TemporaryDirectory() as root:
            calls=[]
            def fake(state, **kw):
                calls.append(kw["slot"])
                return {"status":"completed"}
            result=supervise(root,max_batches=1,runner=fake,
                clock=lambda:datetime(2026,10,28,12,tzinfo=timezone.utc))
            self.assertEqual(len(calls),1)
            self.assertEqual(result["max_model_calls_authorized"],10)
            self.assertFalse(result["live_trading_authorized"])
    def test_manual_review_stops_without_retry(self):
        calls=[]
        def fail(*args,**kwargs):
            calls.append(1)
            return {"status":"requires_manual_review"}
        result=supervise(".",max_batches=3,runner=fail,
            clock=lambda:datetime(2026,10,28,12,tzinfo=timezone.utc))
        self.assertEqual(len(calls),1)
        self.assertEqual(len(result["attempted_slots"]),1)
    def test_missing_api_key_blocks_real_provider(self):
        with patch.dict("os.environ",{"OPENAI_API_KEY":""}):
            with self.assertRaisesRegex(ValueError,"OPENAI_API_KEY"):
                supervise(".",max_batches=1)
    def test_invalid_budget_rejected(self):
        for value in (0,25,True,1.5):
            with self.assertRaises(ValueError):
                supervise(".",max_batches=value)
    def test_launcher_does_not_autorun_paid_model(self):
        text=(Path(__file__).resolve().parents[1]/"launch.py").read_text(encoding="utf-8")
        self.assertIn('default=0, help="明確授權 B+C OpenAI',text)
        self.assertIn('args.openai_ack_calls != 10 * args.openai_batches',text)

if __name__ == "__main__":
    unittest.main()
