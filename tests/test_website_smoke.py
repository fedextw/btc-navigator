"""Isolated Streamlit HTTP smoke check; no scanner or market network calls."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import unittest

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class WebsiteSmokeTests(unittest.TestCase):
    def test_streamlit_health_on_isolated_port(self):
        with tempfile.TemporaryDirectory() as directory:
            port = free_port()
            env = dict(os.environ, BTC_NAVIGATOR_DEMO="1",
                       BTC_NAVIGATOR_STATE_DIR=directory)
            command = [sys.executable, "-m", "streamlit", "run", "btc_app.py",
                       "--server.address=127.0.0.1", f"--server.port={port}",
                       "--server.headless=true", "--browser.gatherUsageStats=false"]
            with (Path(directory) / "web.log").open("w+", encoding="utf-8") as output:
                process = subprocess.Popen(command, cwd=ROOT, env=env,
                                           stdout=output, stderr=subprocess.STDOUT)
                try:
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline:
                        if process.poll() is not None:
                            output.seek(0)
                            self.fail("網站提前退出：" + output.read()[-1500:])
                        try:
                            with urllib.request.urlopen(
                                    f"http://127.0.0.1:{port}/_stcore/health",
                                    timeout=2) as response:
                                if response.status == 200:
                                    break
                        except OSError:
                            time.sleep(.4)
                    else:
                        output.seek(0)
                        self.fail("網站健康端點未就緒：" + output.read()[-1500:])
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=8)


if __name__ == "__main__":
    unittest.main()
