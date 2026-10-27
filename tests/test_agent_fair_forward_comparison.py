import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from agent_fair_forward_comparison import compare_fresh_paper

class FairComparisonTests(unittest.TestCase):
    def test_identical_post_cutoff_window_never_promotes(self):
        start=datetime(2026,1,1,tzinfo=timezone.utc)
        rows=[]
        for i in range(500):
            p=100+i*.05+(i%7)*.03
            rows.append(((start+timedelta(hours=i)).isoformat(),p,p+1,p-1,p+.02,100))
        old=(start+timedelta(hours=100)).isoformat()
        new=(start+timedelta(hours=200)).isoformat()
        with patch("agent_fair_forward_comparison.history_from_database",return_value=rows):
            report=compare_fresh_paper(".", "BTCUSDT","1h",
                                       "trend_8_30","breakout_20",old,new)
        self.assertEqual(report["evaluation_after_utc"],new)
        self.assertIn(report["status"],("insufficient_fresh_trades",
                                        "fresh_paper_comparison_available"))
        self.assertFalse(report["independent_improvement_proven"])
        self.assertFalse(report["live_trading_authorized"])
        self.assertIn("old_metrics",report)
        self.assertIn("new_metrics",report)

    def test_future_cutoff_waits_and_reversed_cutoff_rejected(self):
        start=datetime(2026,1,1,tzinfo=timezone.utc)
        rows=[((start+timedelta(hours=i)).isoformat(),100,101,99,100,50)
              for i in range(300)]
        old=start.isoformat()
        future=(start+timedelta(days=20)).isoformat()
        with patch("agent_fair_forward_comparison.history_from_database",return_value=rows):
            report=compare_fresh_paper(".","BTCUSDT","1h","trend_8_30",
                                       "breakout_20",old,future)
        self.assertEqual(report["status"],"waiting_fresh_candles")
        with self.assertRaises(ValueError):
            compare_fresh_paper(".","BTCUSDT","1h","trend_8_30",
                                "breakout_20",future,old)

if __name__=="__main__":
    unittest.main()
