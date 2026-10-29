import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from agent_stage_four_rotation import run_rotation

class LivePreflightIsolationTests(unittest.TestCase):
    def test_bad_4usdt_is_excluded_before_reserving_model_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            universe={"symbols":["4USDT","BTCUSDT"],"has_more":False}
            checked=[]
            def eligibility(symbol,**kwargs):
                checked.append(symbol)
                return symbol!="4USDT"
            with patch("agent_stage_four_rotation.discover",return_value=universe),\
                 patch("agent_stage_four_rotation.enough_closed_history",side_effect=eligibility),\
                 patch("agent_stage_four_rotation.run_discovered_batch",
                       return_value={"items":[{"symbol":"BTCUSDT","status":"completed"}]}) as batch:
                result=run_rotation(tmp,slot="20261029T06Z")
            self.assertEqual(result["status"],"completed")
            self.assertEqual(checked,["4USDT","BTCUSDT"])
            self.assertEqual(batch.call_args.kwargs["universe_snapshot"]["symbols"],["BTCUSDT"])
            self.assertEqual(result["next_offset"],0)

    def test_none_eligible_never_reserves_paid_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            universe={"symbols":["4USDT"],"has_more":True}
            with patch("agent_stage_four_rotation.discover",return_value=universe),\
                 patch("agent_stage_four_rotation.enough_closed_history",return_value=False),\
                 patch("agent_stage_four_rotation.run_discovered_batch") as batch:
                result=run_rotation(tmp,slot="20261029T06Z")
            self.assertEqual(result["status"],"waiting_for_fresh_data")
            self.assertFalse((Path(tmp)/"stage4-universe-cursor.json").exists())
            batch.assert_not_called()

if __name__=="__main__":
    unittest.main()
