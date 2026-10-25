import unittest
from datetime import datetime,timedelta,timezone
from agent_forward_paper import simulate

def observations(n=120,gap=False):
    start=datetime(2026,10,26,tzinfo=timezone.utc)
    rows=[]
    for i in range(n):
        t=start+timedelta(hours=i+(1 if gap and i>=90 else 0))
        price=100+i*.2
        rows.append({"schema":"agent-forward-observation-v1","status":"observed_not_traded",
                     "live_trading_authorized":False,"research_sha256":"abc",
                     "symbol":"BTCUSDT","strategy":"trend_8_30",
                     "candle_time_utc":t.isoformat(),
                     "close_time_utc":(t+timedelta(minutes=59,seconds=59)).isoformat(),
                     "observed_at_utc":(t+timedelta(hours=1,minutes=1)).isoformat(),
                     "ohlcv":{"open":price,"high":price+2,"low":price-2,"close":price+.1,"volume":100}})
    return rows

class ForwardPaperTests(unittest.TestCase):
    def test_estimates_are_explicitly_paper_only_and_costed(self):
        data=observations()
        a=simulate(data,"trend_8_30",round_trip_cost=.0014)
        b=simulate(data,"trend_8_30",round_trip_cost=.01)
        self.assertGreater(a["trades"],0)
        self.assertGreater(a["net_return_pct"],b["net_return_pct"])
        self.assertTrue(a["not_actual_fills"])
        self.assertFalse(a["live_trading_authorized"])
        for trade in a["trades_detail"]:
            self.assertLess(trade["signal_utc"],trade["entry_utc"])
            self.assertLess(trade["entry_utc"],trade["exit_utc"])

    def test_late_observations_are_retrospective_not_forward_verified(self):
        result=simulate(observations(),"trend_8_30")
        self.assertGreater(result["retrospective_only_trades"],0)
        self.assertEqual(result["prospective_eligible_trades"],0)
        self.assertEqual(result["evidence_status"],"retrospective_only_not_forward_verified")
        self.assertTrue(all(t["prospective_signal_observed_before_entry"] is False
                            for t in result["trades_detail"]))

    def test_late_indicator_history_blocks_prospective_classification(self):
        rows=observations()
        for row in rows:
            row["observed_at_utc"]=row["close_time_utc"][:-6]+"59+00:00" if False else row["close_time_utc"]
        # Produce valid timestamps strictly after close and before next open.
        for row in rows:
            from agent_forward_enrollment import _utc
            row["observed_at_utc"]=(_utc(row["close_time_utc"])+timedelta(microseconds=1)).isoformat()
        timely=simulate(rows,"trend_8_30")
        self.assertGreater(timely["prospective_eligible_trades"],0)
        self.assertIsNotNone(timely["prospective_paper_net_return_pct"])
        rows[0]["observed_at_utc"]=(datetime(2026,10,30,tzinfo=timezone.utc)).isoformat()
        later=simulate(rows,"trend_8_30")
        self.assertEqual(later["prospective_eligible_trades"],0)
        self.assertIsNone(later["prospective_paper_net_return_pct"])

    def test_missing_or_mixed_bars_rejected(self):
        with self.assertRaises(ValueError):
            simulate(observations(gap=True),"trend_8_30")
        d=observations()
        d[-1]["research_sha256"]="other"
        with self.assertRaises(ValueError):
            simulate(d,"trend_8_30")
        with self.assertRaises(ValueError):
            simulate(observations(),"unregistered_strategy")

    def test_empty_waits(self):
        self.assertEqual(simulate([],"trend_8_30")["trades"],0)

if __name__=="__main__":
    unittest.main()
