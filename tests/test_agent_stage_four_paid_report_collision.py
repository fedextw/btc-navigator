import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
import agent_stage_four_delivery as module

class StageFourPaidAcceptanceCollisionTests(unittest.TestCase):
    def test_existing_report_is_rejected_before_paid_rotation(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td)/"stage4-live-acceptance.json").write_text("existing report",encoding="utf-8")
            with patch.object(sys,"argv",["stage4","--state-dir",td,"--slot","20261029T00Z",
                                          "--execute","--allow-model-calls","10"]):
                with patch.object(module,"delivery") as model:
                    with self.assertRaises(SystemExit) as err:
                        module.main()
                    self.assertEqual(err.exception.code,2)
                    model.assert_not_called()
            self.assertEqual((Path(td)/"stage4-live-acceptance.json").read_text(),"existing report")
if __name__=="__main__":
    unittest.main()
