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


    def test_all_ineligible_page_advances_cursor_without_paid_call(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            seen=[]
            def discover_page(**kw):
                seen.append(kw["offset"])
                return {"symbols":["4USDT"] if kw["offset"]==0 else ["BTCUSDT"],
                        "has_more":kw["offset"]==0}
            with patch("agent_stage_four_rotation.discover",side_effect=discover_page),\\
                 patch("agent_stage_four_rotation.enough_closed_history",
                       side_effect=lambda symbol,**kw:symbol=="BTCUSDT"),\\
                 patch("agent_stage_four_rotation.run_discovered_batch",
                       return_value={"items":[{"symbol":"BTCUSDT","status":"completed"}]}) as paid:
                first=run_rotation(tmp,slot="20261029T06Z")
                self.assertEqual(first["status"],"waiting_for_fresh_data")
                self.assertEqual(first["next_offset"],1)
                self.assertEqual(first["paper_only"],True)
                paid.assert_not_called()
                cursor=json.loads((Path(tmp)/"stage4-universe-cursor.json").read_text())
                self.assertEqual(cursor["status"],"completed")
                second=run_rotation(tmp,slot="20261029T12Z")
            self.assertEqual(second["status"],"completed")
            self.assertEqual(seen,[0,1])
            self.assertEqual(paid.call_count,1)

if __name__=="__main__":
    unittest.main()
