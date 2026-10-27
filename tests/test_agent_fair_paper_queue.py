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

    def test_corrupted_request_does_not_block_other_paper_checks(self):
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            comparison={"status":"awaiting_fresh_independent_comparison",
                        "old_strategy":"trend_8_30","new_candidate":"breakout_20",
                        "old_historical_cutoff_utc":"2026-01-01T00:00:00+00:00",
                        "new_research_cutoff_utc":"2026-02-01T00:00:00+00:00",
                        "live_trading_authorized":False}
            save_comparison_request(td,"BTCUSDT","1h",comparison)
            folder=Path(td)/"agent-paper-comparison-requests"
            (folder/("0"*64+".json")).write_text("{invalid",encoding="utf-8")
            with patch("agent_fair_forward_comparison.compare_fresh_paper",
                       return_value={"status":"waiting_fresh_candles",
                                     "live_trading_authorized":False}):
                result=review_comparison_requests(td,limit=2)
            self.assertEqual(result["reviewed"],2)
            self.assertEqual(set(x["status"] for x in result["items"]),
                             {"review_error","waiting_fresh_candles"})
            self.assertFalse(result["live_trading_authorized"])

    def test_restart_uses_existing_requests_without_data_loss(self):
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            request={"status":"awaiting_fresh_independent_comparison",
                     "old_strategy":"trend_8_30","new_candidate":"breakout_20",
                     "old_historical_cutoff_utc":"2026-01-01T00:00:00+00:00",
                     "new_research_cutoff_utc":"2026-02-01T00:00:00+00:00",
                     "live_trading_authorized":False}
            original=save_comparison_request(td,"BTCUSDT","1h",request)
            directory=Path(td)/"agent-paper-comparison-requests"
            initial={p.name:p.read_bytes() for p in directory.glob("*.json")}
            with patch("agent_fair_forward_comparison.compare_fresh_paper",
                       return_value={"status":"waiting_fresh_candles",
                                     "live_trading_authorized":False}):
                first=review_comparison_requests(td,batch_number=0)
                second=review_comparison_requests(td,batch_number=1)
            self.assertEqual(first["items"][0]["request_sha256"],
                             original["request_sha256"])
            self.assertEqual(first["items"],second["items"])
            self.assertEqual(initial,{p.name:p.read_bytes()
                                      for p in directory.glob("*.json")})
            self.assertEqual(original,save_comparison_request(td,"BTCUSDT","1h",request))
            self.assertEqual(len(list(directory.glob("*.json"))),1)

    def test_missing_verified_cutoff_cannot_be_queued(self):
        with tempfile.TemporaryDirectory() as td:
            candidate={"status":"awaiting_fresh_independent_comparison",
                       "old_strategy":"trend_8_30","new_candidate":"breakout_20",
                       "live_trading_authorized":False}
            with self.assertRaises(ValueError):
                save_comparison_request(td,"BTCUSDT","1h",candidate)

if __name__=="__main__":
    unittest.main()
