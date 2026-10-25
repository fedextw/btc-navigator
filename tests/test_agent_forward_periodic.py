import tempfile
import unittest
from agent_forward_periodic import run_periodic

class ForwardPeriodicTests(unittest.TestCase):
    def test_two_cycles_are_serial_and_bounded(self):
        calls=[]
        def runner(path):
            calls.append("run")
            return {"status":"completed","registered":{"registered":1},"observed":{"observed":2}}
        def sleep(seconds):
            calls.append(seconds)
        with tempfile.TemporaryDirectory() as td:
            r=run_periodic(td,interval_seconds=300,cycles=2,sleep=sleep,runner=runner)
            self.assertEqual(calls,["run",300,"run"])
            self.assertEqual(len(r["cycles"]),2)
            self.assertFalse(r["live_trading_authorized"])

    def test_stale_lock_stops_without_retrying(self):
        with tempfile.TemporaryDirectory() as td:
            r=run_periodic(td,interval_seconds=300,cycles=4,sleep=lambda _: self.fail("must not sleep"),
                           runner=lambda _: {"status":"already_running_or_stale_lock"})
            self.assertEqual(len(r["cycles"]),1)
            self.assertEqual(r["status"],"stopped")

    def test_invalid_schedule_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                run_periodic(td,interval_seconds=30)
            with self.assertRaises(ValueError):
                run_periodic(td,cycles=100)

if __name__=="__main__":
    unittest.main()
