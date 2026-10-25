"""Integration smoke: actual launcher creates isolated UI/scanner/agent processes.

Use demo mode, disposable state, a dynamically selected port; no trading keys.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import unittest

ROOT=Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0))
        return sock.getsockname()[1]


class FullStackSmokeTest(unittest.TestCase):
    def test_demo_launcher_starts_and_stops_three_services(self):
        with tempfile.TemporaryDirectory() as td:
            state=Path(td)
            port=free_port()
            env=os.environ.copy()
            env["BTC_NAVIGATOR_STATE_DIR"]=td
            env["PYTHONIOENCODING"]="utf-8"
            command=[sys.executable,"launch.py","--ready","--demo",
                     "--no-browser","--port",str(port),"--agent-research",
                     "--demo-test-stop"]
            process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT)
            try:
                deadline=time.monotonic()+65
                while time.monotonic()<deadline:
                    if process.poll() is not None:
                        self.fail(f"啟動器提前停止：{process.returncode}")
                    healthy=False
                    try:
                        with urllib.request.urlopen(
                                f"http://127.0.0.1:{port}/_stcore/health",timeout=2) as response:
                            healthy=response.status==200
                    except OSError:
                        pass
                    scanner_log=state/"scanner.log"
                    status=state/"agent-status"/"latest.json"
                    if healthy and scanner_log.exists() and status.exists():
                        data=json.loads(status.read_text(encoding="utf-8"))
                        self.assertFalse(data["live_trading_authorized"])
                        self.assertIn(data["phase"],("running","completed","error"))
                        break
                    time.sleep(.5)
                else:
                    self.fail("無法同時觀察到網站、掃描程序與 Agent 狀態")
            finally:
                # Normal cooperative exit: parent stops and reaps all children.
                (state / ".demo-test-stop").touch()
                try:
                    process.wait(timeout=22)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
                self.assertEqual(process.returncode, 0, "啟動器無法正常結束")
                # Verify the child website actually released its port.
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    with socket.socket() as probe:
                        if probe.connect_ex(("127.0.0.1", port)) != 0:
                            break
                    time.sleep(.2)
                else:
                    self.fail("網站子程序仍佔用測試連接埠")


if __name__=="__main__":
    unittest.main()
