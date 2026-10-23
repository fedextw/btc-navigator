import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import bootstrap


class StartupTests(unittest.TestCase):
    def write_app(self, root, script):
        for name in ("btc_app.py", "dashboard.py", "collector.py", "market_data.py", "requirements.txt", "scanner.py"):
            (root / name).write_text("", encoding="utf-8")
        (root / "launch.py").write_text(script, encoding="utf-8")

    def test_child_error_is_displayed_logged_and_propagated(self):
        with tempfile.TemporaryDirectory(prefix="btc-startup-") as directory:
            root = Path(directory) / "中文 folder"
            root.mkdir()
            self.write_app(root, "import sys\nprint('套件安裝失敗：example', flush=True)\nsys.exit(23)\n")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = bootstrap.run([], root)
            self.assertEqual(status, 23)
            self.assertIn("套件安裝失敗", output.getvalue())
            self.assertIn("Launcher exit code: 23", (root / "startup.log").read_text(encoding="utf-8"))

    def test_incomplete_zip_has_actionable_message(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            with patch("bootstrap.subprocess.Popen") as child:
                status = bootstrap.run([], root)
            self.assertEqual(status, 1)
            child.assert_not_called()
            self.assertIn("Extract the ENTIRE ZIP", (root / "startup.log").read_text())

    def test_old_python_is_reported_before_dependency_install(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            with patch("bootstrap.sys.version_info", (3, 10)), patch("bootstrap.subprocess.Popen") as child:
                self.assertEqual(bootstrap.run([], root), 1)
            child.assert_not_called()
            self.assertIn("Python 3.11 or newer", (root / "startup.log").read_text())

    def test_success_and_stderr_are_both_retained(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            self.write_app(root, "import sys\nprint('ready')\nprint('diagnostic',file=sys.stderr)\n")
            self.assertEqual(bootstrap.run([], root), 0)
            log = (root / "startup.log").read_text()
            self.assertIn("ready", log)
            self.assertIn("diagnostic", log)
            self.assertIn("Launcher exit code: 0", log)


if __name__ == "__main__":
    unittest.main()
