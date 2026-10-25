import json
import tempfile
import unittest
from pathlib import Path
from agent_stage5_batch import review_enrolled

class Stage5BatchTests(unittest.TestCase):
    def test_registered_candidate_gets_real_replay_and_fail_closed_review(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)/"agent-forward"
            folder.mkdir()
            (folder/"candidate.json").write_text(json.dumps({
                "schema":"agent-forward-enrollment-v1","symbol":"BTCUSDT",
                "strategy":"trend_8_30","research_sha256":"abc123",
                "enrolled_at_utc":"2026-10-26T00:00:00Z",
                "live_trading_authorized":False}),encoding="utf-8")
            output=review_enrolled(td,now="2026-10-26T10:00:00Z")
            self.assertEqual(output["checked"],1)
            self.assertEqual(output["candidates"][0]["decision"]["status"],"hold_for_review")
            self.assertFalse(output["automatic_promotion_authorized"])
            self.assertFalse(output["live_trading_authorized"])
            self.assertEqual(output["candidates"][0]["symbol"],"BTCUSDT")

    def test_corrupt_enrollment_is_blocked_but_other_candidates_continue(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)/"agent-forward"
            folder.mkdir()
            (folder/"a.json").write_text("not json",encoding="utf-8")
            (folder/"b.json").write_text(json.dumps({
                "schema":"agent-forward-enrollment-v1","symbol":"ETHUSDT",
                "strategy":"trend_8_30","research_sha256":"def123",
                "enrolled_at_utc":"2026-10-26T00:00:00Z",
                "live_trading_authorized":False}),encoding="utf-8")
            output=review_enrolled(td,now="2026-10-26T10:00:00Z")
            self.assertEqual(output["checked"],2)
            self.assertTrue(all(x["decision"]["status"]=="hold_for_review" for x in output["candidates"]))
            self.assertEqual(output["candidates"][1]["symbol"],"ETHUSDT")

if __name__=="__main__":
    unittest.main()
