import unittest
from agent_stage5_cycle import run_rotation

class Stage5RotationTests(unittest.TestCase):
    def test_multiple_batches_progress_sequentially(self):
        seen=[]
        def run(state,*,batch_number):
            seen.append(batch_number)
            return {"schema":"agent-stage5-cycle-v1","research":{"counts":{"attempted":1,"completed":1},"items":[{"status":"completed"}]},
                    "automatic_promotion_authorized":False,
                    "live_trading_authorized":False}
        result=run_rotation("/unused",rounds=3,start_batch=4,cycle_runner=run)
        self.assertEqual(seen,[4,5,6])
        self.assertEqual(result["completed_cycles"],3)
        self.assertFalse(result["live_trading_authorized"])
    def test_no_ready_symbols_stops_loop(self):
        seen=[]
        def run(state,*,batch_number):
            seen.append(batch_number)
            return {"schema":"agent-stage5-cycle-v1",
                    "status":"waiting_for_research_ready_symbols",
                    "automatic_promotion_authorized":False,
                    "live_trading_authorized":False}
        result=run_rotation("/unused",rounds=5,cycle_runner=run)
        self.assertEqual(seen,[0])
        self.assertEqual(result["completed_cycles"],0)
    def test_invalid_or_unsafe_cycle_fails(self):
        with self.assertRaises(ValueError):
            run_rotation("/unused",rounds=11)
        with self.assertRaises(ValueError):
            run_rotation("/unused",cycle_runner=lambda *a,**k:{
                "schema":"agent-stage5-cycle-v1",
                "automatic_promotion_authorized":True,
                "live_trading_authorized":False})

if __name__=="__main__":
    unittest.main()
