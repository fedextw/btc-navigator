import tempfile
import unittest
from unittest.mock import patch
from agent_fair_paper_queue import save_comparison_request, review_comparison_requests

class FairPaperQueueTests(unittest.TestCase):
    def test_idempotent_request_and_safe_review(self):
        with tempfile.TemporaryDirectory() as td:
            comparison={"status":"awaiting_fresh_independent_comparison",
                        "old_strategy":"trend_8_30",
                        "new_candidate":"breakout_20",
                        "old_historical_cutoff_utc":"2026-01-01T00:00:00+00:00",
                        "new_research_cutoff_utc":"2026-02-01T00:00:00+00:00",
                        "live_trading_authorized":False}
            first=save_comparison_request(td,"BTCUSDT","1h",comparison)
            second=save_comparison_request(td,"BTCUSDT","1h",comparison)
            self.assertEqual(first,second)
            with patch("agent_fair_forward_comparison.compare_fresh_paper",
                       return_value={"status":"waiting_fresh_candles",
                                     "live_trading_authorized":False}) as mock:
                batch=review_comparison_requests(td)
            self.assertEqual(batch["total_requests"],1)
            self.assertEqual(batch["items"][0]["status"],"waiting_fresh_candles")
            self.assertEqual(mock.call_count,1)
            self.assertFalse(batch["automatic_promotion_authorized"])

    def test_missing_verified_cutoff_cannot_be_queued(self):
        with tempfile.TemporaryDirectory() as td:
            candidate={"status":"awaiting_fresh_independent_comparison",
                       "old_strategy":"trend_8_30","new_candidate":"breakout_20",
                       "live_trading_authorized":False}
            with self.assertRaises(ValueError):
                save_comparison_request(td,"BTCUSDT","1h",candidate)

if __name__=="__main__":
    unittest.main()
