"""Verify real delivered ZIP contents after extraction, not only source tree."""
from pathlib import Path
import tempfile
import os
import json
import socket
import time
import urllib.request
import subprocess
import sys
import unittest
import zipfile

from agent_build_release import build, PACKAGE_NAME
from agent_release_preflight import inspect
from agent_package_integrity import verify_package


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
            self.assertTrue(verify_package(package),"Release SHA256 integrity mismatch")
            integrity=subprocess.run([sys.executable,"agent_package_integrity.py",
                                      "--root",str(package)],
                                     cwd=package,capture_output=True,text=True,
                                     encoding="utf-8",errors="replace",timeout=30)
            self.assertEqual(integrity.returncode,0,integrity.stdout+integrity.stderr)
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
            # Real extracted stage-five CLI must wait safely on an empty workspace.
            stage5=subprocess.run([sys.executable,"agent_stage5_cycle.py",
                                   "--state-dir",str(package/".agent-test-state"),
                                   "--rounds","2","--resume"],
                                  cwd=package,capture_output=True,text=True,
                                  encoding="utf-8",errors="replace",timeout=30)
            self.assertEqual(stage5.returncode,0,stage5.stdout+stage5.stderr)
            self.assertIn("waiting_for_research_ready_symbols",stage5.stdout)
            self.assertIn('"live_trading_authorized": false',stage5.stdout)
            self.assertFalse((package/".agent-test-state"/"agent-stage5-rotation-progress.json").exists())
            # Normal Python bytecode caches must not invalidate an installed package.
            self.assertTrue(verify_package(package))
            (package/"startup.log").write_text("startup log",encoding="utf-8")
            (package/".launcher-venv").mkdir()
            (package/".launcher-venv"/"runtime.txt").write_text("runtime",encoding="utf-8")
            self.assertTrue(verify_package(package),"Normal launcher output must not invalidate package")
            self.assertIn("agent_package_integrity.py",(package/"START_BC_RESEARCH_TEST.bat").read_text(encoding="utf-8"))
            self.assertIn("if errorlevel 1",(package/"START_BC_RESEARCH_TEST.bat").read_text(encoding="utf-8"))
            self.assertFalse((package/".local-state").exists())
            self.assertFalse((package/".env").exists())
            # Corrupt one real extracted file and prove verification detects it.
            victim=package/"agent_stage5_cycle.py"
            victim.write_bytes(victim.read_bytes()+b"\\n# corrupted")
            self.assertFalse(verify_package(package))
            integrity_bad=subprocess.run([sys.executable,"agent_package_integrity.py"],
                                         cwd=package,capture_output=True,text=True,
                                         encoding="utf-8",errors="replace",timeout=30)
            self.assertEqual(integrity_bad.returncode,2,integrity_bad.stdout+integrity_bad.stderr)
            victim.write_bytes(victim.read_bytes().removesuffix(b"\\n# corrupted"))
            self.assertTrue(verify_package(package))
            check=subprocess.run([sys.executable,"launch.py","--ready","--check"],
                                 cwd=package,capture_output=True,text=True,
                                 encoding="utf-8",errors="replace",timeout=30)
            self.assertEqual(check.returncode,0,check.stdout+check.stderr)


    def test_extracted_package_launches_complete_demo_services(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            archive=Path(td)/"release.zip"
            build(root,archive)
            with zipfile.ZipFile(archive) as z:
                z.extractall(Path(td)/"unpacked")
            package=Path(td)/"unpacked"/PACKAGE_NAME
            with socket.socket() as sock:
                sock.bind(("127.0.0.1",0))
                port=sock.getsockname()[1]
            state=Path(td)/"disposable-state"
            state.mkdir()
            env=os.environ.copy()
            env["BTC_NAVIGATOR_STATE_DIR"]=str(state)
            env["PYTHONIOENCODING"]="utf-8"
            process=subprocess.Popen([sys.executable,"launch.py","--ready","--demo",
                    "--no-browser","--port",str(port),"--agent-research","--demo-test-stop"],
                    cwd=package,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT)
            try:
                deadline=time.monotonic()+65
                while time.monotonic()<deadline:
                    self.assertIsNone(process.poll(),"Extracted release launcher exited early")
                    try:
                        with urllib.request.urlopen(
                            "http://127.0.0.1:"+str(port)+"/_stcore/health",timeout=2) as r:
                            web_ready=r.status==200
                    except OSError:
                        web_ready=False
                    status=state/"agent-status"/"latest.json"
                    if web_ready and (state/"scanner.log").is_file() and status.is_file():
                        data=json.loads(status.read_text(encoding="utf-8"))
                        self.assertFalse(data["live_trading_authorized"])
                        break
                    time.sleep(.5)
                else:
                    self.fail("Extracted release website/scanner/research never all became ready")
            finally:
                (state/".demo-test-stop").touch()
                try:
                    process.wait(timeout=22)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
                self.assertEqual(process.returncode,0)


if __name__=="__main__":
    unittest.main()
