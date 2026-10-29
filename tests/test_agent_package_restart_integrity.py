import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from agent_package_integrity import verify_package

class PackageRestartIntegrityTests(unittest.TestCase):
    def test_runtime_research_state_does_not_break_second_launch(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            payload=b"safe offline application"
            (root/"main.py").write_bytes(payload)
            (root/"PACKAGE_SHA256.json").write_text(json.dumps({
                "schema":"agent-package-sha256-v1",
                "files":{"main.py":hashlib.sha256(payload).hexdigest()}
            }),encoding="utf-8")
            self.assertTrue(verify_package(root))
            for dirname in (".agent-test-state",".local-state","stage4-openai"):
                target=root/dirname/"markets"/"BTCUSDT"
                target.mkdir(parents=True)
                (target/"research.json").write_text("{}",encoding="utf-8")
            self.assertTrue(verify_package(root))
            (root/"main.py").write_bytes(b"tampered")
            self.assertFalse(verify_package(root))

    def test_unknown_extra_source_still_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            raw=b"safe"
            (root/"main.py").write_bytes(raw)
            (root/"PACKAGE_SHA256.json").write_text(json.dumps({
                "schema":"agent-package-sha256-v1",
                "files":{"main.py":hashlib.sha256(raw).hexdigest()}
            }),encoding="utf-8")
            (root/"unexpected.py").write_text("print('bad')",encoding="utf-8")
            self.assertFalse(verify_package(root))
if __name__=="__main__":
    unittest.main()
