import json
import tempfile
import unittest
from pathlib import Path
from agent_research_panel import load_status


class AgentPanelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root/"agent-status").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def save(self, payload):
        (self.root/"agent-status"/"latest.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_no_status_is_safe(self):
        self.assertEqual(load_status(self.root)["state"], "not_started")

    def test_display_result_without_trade_authorization(self):
        self.save({"schema":"agent-scheduler-v1","paper_only":True,
                   "live_trading_authorized":False,
                   "items":[{"symbol":"BTCUSDT","at":"2026-10-25T00:00:00Z",
                             "status":"completed","result":{"selected":"trend_10_50",
                             "status":"rejected","reason":"樣本不足","bars":300}}]})
        x=load_status(self.root)
        self.assertEqual(x["state"],"available")
        self.assertEqual(x["items"][0]["decision"],"rejected")

    def test_rejects_unrecognized_or_authorized_status(self):
        self.save({"schema":"agent-scheduler-v1","live_trading_authorized":True,"items":[]})
        self.assertEqual(load_status(self.root)["state"],"invalid")
        self.save({"schema":"unknown","live_trading_authorized":False,"items":[]})
        self.assertEqual(load_status(self.root)["state"],"invalid")

    def test_corrupt_and_oversize(self):
        path=self.root/"agent-status"/"latest.json"
        path.write_text("{",encoding="utf-8")
        self.assertEqual(load_status(self.root)["state"],"invalid")
        path.write_text("x"*256001,encoding="utf-8")
        self.assertEqual(load_status(self.root)["state"],"invalid")


if __name__=="__main__":
    unittest.main()
