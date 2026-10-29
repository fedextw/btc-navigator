import json
import hashlib
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

from agent_stage_four_readiness import check_batch_readiness
from agent_stage_four_rotation import run_rotation


class FreshnessGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.symbol = "BTCUSDT"

    def make_checkpoint(self, status="completed", latest="2026-10-01T00:00:00+00:00"):
        path = self.root / "markets" / self.symbol / "1h"
        path.mkdir(parents=True)
        raw=json.dumps({"schema":"agent-orchestrator-v1","paper_only":True,
                        "dataset_latest_utc":latest}).encode("utf-8")
        report=path/(hashlib.sha256(raw).hexdigest()+".json")
        report.write_bytes(raw)
        (path / "stage4-checkpoint.json").write_text(json.dumps({
            "schema": "agent-stage4-checkpoint-v1", "status": status,
            "report_path": str(report)}), encoding="utf-8")

    def test_modified_report_never_controls_freshness(self):
        self.make_checkpoint()
        folder=self.root/"markets"/self.symbol/"1h"
        report=Path(json.loads((folder/"stage4-checkpoint.json").read_text(encoding="utf-8"))["report_path"])
        report.write_bytes(report.read_bytes()+b" ")
        with self.assertRaisesRegex(ValueError,"checksum"):
            check_batch_readiness(self.root,[self.symbol])
    def test_bootstrap_is_ready(self):
        result = check_batch_readiness(self.root, [self.symbol], now=datetime(
            2026, 10, 2, tzinfo=timezone.utc))
        self.assertEqual(result["status"], "ready")

    def test_insufficient_closed_candles_waits_without_model_call(self):
        self.make_checkpoint()
        now = datetime(2026, 10, 2, tzinfo=timezone.utc)
        result = check_batch_readiness(self.root, [self.symbol], now=now)
        self.assertEqual(result["status"], "waiting_for_fresh_data")
        self.assertEqual(result["waiting"][0]["symbol"], self.symbol)

    def test_expected_data_wait_does_not_reserve_rotation(self):
        # No account key or external request; only the discovery HTTP is mocked.
        self.make_checkpoint(latest=datetime.now(timezone.utc).isoformat())
        discovery = {"symbols": [self.symbol], "has_more": False}
        with patch("agent_stage_four_rotation.discover", return_value=discovery), patch(
            "agent_stage_four_rotation.enough_closed_history", return_value=True), patch(
            "agent_stage_four_rotation.run_discovered_batch") as research:
            result = run_rotation(self.root, slot="NEW")
        self.assertEqual(result["status"], "waiting_for_fresh_data")
        research.assert_not_called()
        self.assertFalse((self.root / "stage4-universe-cursor.json").exists())

    def test_interrupted_previous_call_requires_review(self):
        self.make_checkpoint(status="reserved")
        result = check_batch_readiness(self.root, [self.symbol])
        self.assertEqual(result["status"], "requires_manual_review")

    def test_sufficient_elapsed_time_allows_attempt_not_guaranteed_validation(self):
        self.make_checkpoint()
        result = check_batch_readiness(self.root, [self.symbol],
            now=datetime(2026, 12, 1, tzinfo=timezone.utc))
        self.assertEqual(result["status"], "ready")


if __name__ == "__main__":
    unittest.main()
