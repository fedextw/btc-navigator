import json
import tempfile
import unittest
from pathlib import Path
from agent_stage5_batch import review_enrolled, save_review_snapshot

class Stage5SnapshotTests(unittest.TestCase):
    def test_review_snapshot_is_reusable_and_cannot_grant_live_trading(self):
        with tempfile.TemporaryDirectory() as td:
            report=review_enrolled(td,now="2026-10-26T10:00:00Z")
            path=save_review_snapshot(td,report)
            self.assertEqual(path,save_review_snapshot(td,report))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")),report)
            self.assertEqual(len(list((Path(td)/"agent-stage5-decisions").glob("*.json"))),1)
            self.assertFalse(report["automatic_promotion_authorized"])
            self.assertFalse(report["live_trading_authorized"])
            rejected=dict(report,live_trading_authorized=True)
            with self.assertRaises(ValueError):
                save_review_snapshot(td,rejected)
    def test_no_silent_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            report=review_enrolled(td)
            path=save_review_snapshot(td,report)
            path.write_text("tampered",encoding="utf-8")
            with self.assertRaises(RuntimeError):
                save_review_snapshot(td,report)

if __name__=="__main__":
    unittest.main()
