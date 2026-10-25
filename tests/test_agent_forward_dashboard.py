import json
import tempfile
import unittest
from pathlib import Path
from agent_forward_dashboard import summarize_forward

class ForwardDashboardTests(unittest.TestCase):
    def test_missing_ledger_does_not_claim_profit(self):
        with tempfile.TemporaryDirectory() as td:
            result=summarize_forward(td)
            self.assertEqual(result["rows"],[])
            self.assertEqual(result["status"],"not_started")

    def test_enrolled_but_no_observations_is_waiting(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)/"agent-forward"
            folder.mkdir()
            entry={"schema":"agent-forward-enrollment-v1",
                   "symbol":"BTCUSDT","strategy":"trend_8_30",
                   "research_sha256":"abc123",
                   "enrolled_at_utc":"2026-10-25T00:00:00Z",
                   "live_trading_authorized":False}
            (folder/"one.json").write_text(json.dumps(entry),encoding="utf-8")
            row=summarize_forward(td)["rows"][0]
            self.assertEqual(row["驗證狀態"],"等待新行情")
            self.assertEqual(row["前向交易筆數"],0)
            self.assertIsNone(row["模擬淨報酬％"])

    def test_invalid_enrollment_cannot_claim_success(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)/"agent-forward"
            folder.mkdir()
            (folder/"invalid.json").write_text('{"schema":"fake","live_trading_authorized":true}',encoding="utf-8")
            row=summarize_forward(td)["rows"][0]
            self.assertEqual(row["驗證狀態"],"資料異常，未計入")

if __name__=="__main__":
    unittest.main()
