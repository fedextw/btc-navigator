import unittest
from datetime import datetime,timedelta,timezone
from agent_strategy_proposals import validate
from agent_research_cycle import make_signals

class MeanReversionResearchTests(unittest.TestCase):
    def test_schema_requires_bounded_threshold(self):
        spec={"family":"mean_reversion","lookback":10,"slow":25,
              "rationale":"hypothesis about overextended candles"}
        self.assertEqual(validate(spec)[1],"mean_reversion")
        for threshold in (0,101,-1):
            with self.assertRaises(ValueError):
                validate(dict(spec,slow=threshold))
    def test_countertrend_and_past_only_reference(self):
        origin=datetime(2025,1,1,tzinfo=timezone.utc)
        bars=[]
        for i in range(120):
            close=100 if i<100 else (103 if i==100 else 97 if i==101 else 100)
            bars.append((origin+timedelta(hours=i),close,close+1,close-1,close,100))
        candidate=validate({"family":"mean_reversion","lookback":10,
                            "slow":20,"rationale":"countertrend test"})
        signals=make_signals(bars,candidate)
        self.assertEqual(signals[100],-1)
        self.assertEqual(signals[101],1)
        self.assertEqual(signals[99],0)
    def test_unknown_family_never_falls_through_to_breakout(self):
        origin=datetime(2025,1,1,tzinfo=timezone.utc)
        candles=[(origin+timedelta(hours=i),100,101,99,100,10) for i in range(120)]
        with self.assertRaisesRegex(ValueError,"Unknown signal family"):
            make_signals(candles,("bad","unknown",10,0))
if __name__=="__main__":
    unittest.main()
