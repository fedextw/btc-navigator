import unittest
from datetime import datetime,timezone,timedelta
from agent_stage_four_periodic import utc_slot,run_period

class StageFourPeriodicTests(unittest.TestCase):
    def test_utc_slot_rounding(self):
        now=datetime(2026,10,28,10,59,tzinfo=timezone.utc)
        self.assertEqual(utc_slot(now,6),"20261028T06Z")
        self.assertEqual(utc_slot(now,1),"20261028T10Z")
        self.assertEqual(utc_slot(now,24),"20261028T00Z")
    def test_no_local_or_offset_time(self):
        with self.assertRaises(ValueError):
            utc_slot(datetime(2026,10,28,10),6)
        with self.assertRaises(ValueError):
            utc_slot(datetime(2026,10,28,10,tzinfo=timezone(timedelta(hours=8))),6)
    def test_period_passes_single_deterministic_slot(self):
        calls=[]
        def fake(state,prior,**kw):
            calls.append(kw)
            return {"status":"already_completed","paper_only":True,
                    "live_trading_authorized":False}
        output=run_period("x","prior",now=datetime(2026,10,28,10,tzinfo=timezone.utc),
                          runner=fake,hours=6)
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]["slot"],"20261028T06Z")
        self.assertFalse(output["live_trading_authorized"])
    def test_invalid_cadence_rejected_before_runner(self):
        calls=[]
        with self.assertRaises(ValueError):
            run_period("x","prior",hours=5,runner=lambda *args,**kw:calls.append(True))
        self.assertFalse(calls)
if __name__=="__main__":
    unittest.main()
