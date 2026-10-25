"""Verify real delivered ZIP contents after extraction, not only source tree."""
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
import zipfile

from agent_build_release import build, PACKAGE_NAME
from agent_release_preflight import inspect


class ExtractedReleaseTests(unittest.TestCase):
    def test_extracted_package_passes_preflight_and_entrypoint_check(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            archive=Path(td)/"test-release.zip"
            build(root,archive)
            extraction=Path(td)/"unpacked"
            extraction.mkdir()
            with zipfile.ZipFile(archive) as z:
                for member in z.infolist():
                    target=(extraction/member.filename).resolve()
                    if not target.is_relative_to(extraction.resolve()):
                        raise AssertionError("ZIP path traversal")
                z.extractall(extraction)
            package=extraction/PACKAGE_NAME
            report=inspect(package)
            self.assertTrue(report["ready"],report)
            self.assertTrue((package/"START_BC_RESEARCH_TEST.bat").is_file())
            self.assertTrue((package/"agent_research_scheduler.py").is_file())
            for module in ("agent_stage5_cycle.py","agent_stage5_batch.py",
                           "agent_stage5_review.py","agent_stage5_ranking.py",
                           "agent_stage6_delivery_gate.py"):
                self.assertTrue((package/module).is_file(),module)
            # Smoke-test the actual EXTRACTED entrypoints, not the checkout.
            stage6=subprocess.run([sys.executable,"agent_stage6_delivery_gate.py",
                                   "--state-dir",str(package/".agent-test-state")],
                                  cwd=package,capture_output=True,text=True,
                                  encoding="utf-8",errors="replace",timeout=30)
            self.assertEqual(stage6.returncode,2,stage6.stdout+stage6.stderr)
            self.assertIn("not_ready_for_delivery",stage6.stdout)
            self.assertFalse((package/".local-state").exists())
            self.assertFalse((package/".env").exists())
            check=subprocess.run([sys.executable,"launch.py","--ready","--check"],
                                 cwd=package,capture_output=True,text=True,
                                 encoding="utf-8",errors="replace",timeout=30)
            self.assertEqual(check.returncode,0,check.stdout+check.stderr)


if __name__=="__main__":
    unittest.main()
