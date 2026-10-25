"""Release artifact must be clean, complete and independently inspectable."""
from pathlib import Path
import tempfile
import unittest
import zipfile
from agent_build_release import build, PACKAGE_NAME
from agent_release_preflight import ESSENTIAL


class ReleaseBuildTests(unittest.TestCase):
    def test_package_contains_required_files_and_no_private_state(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            archive=Path(td)/"bc-test.zip"
            build(root,archive)
            with zipfile.ZipFile(archive) as zip_file:
                names=set(zip_file.namelist())
                for required in ESSENTIAL:
                    self.assertIn(f"{PACKAGE_NAME}/{required}",names)
                self.assertFalse(any("/tests/" in x or "/.github/" in x or
                                     "/.local-state/" in x or "/.agent-test-state/" in x or
                                     "/.env" in x or "__pycache__" in x
                                     for x in names))
            with self.assertRaises(FileExistsError):
                build(root,archive)


if __name__=="__main__":
    unittest.main()
