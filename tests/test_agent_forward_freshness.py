import tempfile
import unittest
from agent_forward_health import append_status
from agent_forward_freshness import assess_freshness

class FreshnessTests(unittest.TestCase):
    def test_empty_stale_and_recent(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(assess_freshness(td)["state"],"not_started")
            append_status(td,{"status":"completed","cycles":[],"live_trading_authorized":False},
                          stamp="2026-10-25T10:00:00Z")
            self.assertEqual(assess_freshness(td,now="2026-10-25T11:00:00Z")["state"],"recently_completed")
            self.assertEqual(assess_freshness(td,now="2026-10-25T14:00:00Z")["state"],"stale")
    def test_stopped_overrides_freshness(self):
        with tempfile.TemporaryDirectory() as td:
            append_status(td,{"status":"stopped","cycles":[],"live_trading_authorized":False},
                          stamp="2026-10-25T10:00:00Z")
            r=assess_freshness(td,now="2026-10-25T10:01:00Z")
            self.assertEqual(r["state"],"execution_stopped")
            self.assertFalse(r["live_trading_authorized"])
    def test_future_date_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            append_status(td,{"status":"completed","cycles":[],"live_trading_authorized":False},
                          stamp="2026-10-25T15:00:00Z")
            self.assertEqual(assess_freshness(td,now="2026-10-25T10:00:00Z")["state"],"invalid")

if __name__=="__main__":
    unittest.main()
