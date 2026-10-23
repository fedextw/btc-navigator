"""Standard-library desktop entry point: show failures and retain a startup log."""
from datetime import datetime
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile


def terminate(child):
    if child is not None and child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=15)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def handle_termination(_signum, _frame):
    raise KeyboardInterrupt


def run(arguments=None, root=None):
    root = Path(root or Path(__file__).resolve().parent)
    arguments = sys.argv[1:] if arguments is None else arguments
    log_path = root / "startup.log"
    try:
        log = log_path.open("w", encoding="utf-8")
    except OSError:
        log_path = Path(tempfile.gettempdir()) / "btc-navigator-startup.log"
        log = log_path.open("w", encoding="utf-8")
    def write(message):
        text = str(message)
        print(text, flush=True)
        log.write(text + "\n")
        log.flush()
    child = None
    try:
        write("BTC Navigator startup / " + datetime.now().isoformat(timespec="seconds"))
        write("Python: " + sys.version.split()[0])
        write("Startup log: " + str(log_path))
        if sys.version_info < (3, 11):
            write("ERROR: Python 3.11 or newer is required. Install Python 3.11 from https://www.python.org/downloads/ and enable Add Python to PATH.")
            return 1
        required = ("launch.py", "btc_app.py", "dashboard.py", "collector.py", "market_data.py", "requirements.txt")
        missing = [name for name in required if not (root / name).is_file()]
        if missing:
            write("ERROR: Missing application files: " + ", ".join(missing))
            write("Extract the ENTIRE ZIP to a writable folder. Do not run a single file inside the ZIP.")
            return 1
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        environment["PYTHONUTF8"] = "1"
        child = subprocess.Popen([sys.executable, "-u", str(root / "launch.py"), *arguments],
            cwd=root, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1)
        for line in child.stdout:
            write(line.rstrip("\r\n"))
        status = child.wait()
        write("Launcher exit code: " + str(status))
        if status:
            write("Startup failed. Keep this window open and inspect startup.log for the actual error above.")
        return status
    except KeyboardInterrupt:
        write("Stopping website and background worker...")
        return 0
    except OSError as error:
        write("ERROR: " + str(error))
        return 1
    finally:
        terminate(child)
        if child is not None and child.stdout is not None:
            child.stdout.close()
        log.close()


if __name__ == "__main__":
    # launch.py handles SIGTERM so its own UI/worker are cleaned up as well.
    signal.signal(signal.SIGTERM, handle_termination)
    raise SystemExit(run())
