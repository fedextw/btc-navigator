import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from agent_forward_batch import review_frozen_batch

class ForwardBatchTests(unittest.TestCase):
    def test_bounded_rotation_and_safe_failures(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)/"agent-frozen-paper-candidates"
            folder.mkdir()
            for i in range(7):
                (folder/f"{i:064x}.json").write_text("{}",encoding="utf-8")
            seen=[]
            def reviewer(root,path):
                seen.append(path.stem)
                if path.stem.endswith("2"):
                    raise ValueError("bad input")
                return {"status":"waiting_new_closed_candles","live_trading_authorized":False}
            with patch("agent_forward_batch.review_frozen_candidate",side_effect=reviewer):
                a=review_frozen_batch(td,limit=3,batch_number=0)
                b=review_frozen_batch(td,limit=3,batch_number=1)
            self.assertEqual(a["reviewed"],3)
            self.assertEqual(b["reviewed"],3)
            self.assertEqual(len(set(seen)),6)
            self.assertIn("review_error",[x["status"] for x in a["items"]])
            self.assertFalse(a["automatic_promotion_authorized"])
    def test_invalid_arguments_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                review_frozen_batch(td,limit=20)
            with self.assertRaises(ValueError):
                review_frozen_batch(td,batch_number=-1)
if __name__=="__main__":
    unittest.main()
