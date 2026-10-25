"""Disposable recovery drill for paper-forward exclusive locks and restart.

Never removes pre-existing locks; no exchange requests or live order paths.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_forward_guarded import guarded_run

class RecoveryDrillTests(unittest.TestCase):
    def test_crash_releases_own_lock_and_allows_clean_retry(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            lock=root/"agent-forward-pipeline.lock"
            with patch("agent_forward_guarded.run_once",side_effect=RuntimeError("injected worker crash")):
                with self.assertRaisesRegex(RuntimeError,"injected worker crash"):
                    guarded_run(td)
            self.assertFalse(lock.exists())
            first=guarded_run(td,now="2026-10-25T12:00:00Z")
            self.assertEqual(first["status"],"completed")
            self.assertFalse(first["live_trading_authorized"])
            self.assertFalse(lock.exists())
            second=guarded_run(td,now="2026-10-25T12:00:00Z")
            self.assertEqual(second["status"],"completed")
            self.assertFalse(lock.exists())

    def test_existing_lock_cannot_be_stolen_even_if_old(self):
        with tempfile.TemporaryDirectory() as td:
            lock=Path(td)/"agent-forward-pipeline.lock"
            lock.write_text(json.dumps({"purpose":"paper_forward_pipeline","pid":99999}),encoding="utf-8")
            before=lock.read_bytes()
            with patch("agent_forward_guarded.run_once") as run:
                blocked=guarded_run(td)
                run.assert_not_called()
            self.assertEqual(blocked["status"],"already_running_or_stale_lock")
            self.assertEqual(lock.read_bytes(),before)

    def test_reentrant_call_blocks_but_outer_call_completes(self):
        with tempfile.TemporaryDirectory() as td:
            nested=[]
            def inner(root,now=None):
                nested.append(guarded_run(root,now=now))
                return {"status":"completed","live_trading_authorized":False}
            with patch("agent_forward_guarded.run_once",side_effect=inner):
                outer=guarded_run(td)
            self.assertEqual(outer["status"],"completed")
            self.assertEqual(nested[0]["status"],"already_running_or_stale_lock")
            self.assertFalse((Path(td)/"agent-forward-pipeline.lock").exists())

if __name__=="__main__":
    unittest.main()
