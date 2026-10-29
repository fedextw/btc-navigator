import tempfile
import unittest
from pathlib import Path
from agent_research_cursor import read_cursor,save_cursor,fully_completed

class AutoUniverseCursorTests(unittest.TestCase):
    def test_resume_and_fail_closed_partial_batch(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(read_cursor(td),0)
            complete={"counts":{"attempted":2,"completed":2},
                      "items":[{"status":"completed"},{"status":"completed"}]}
            partial={"counts":{"attempted":2,"completed":1},
                     "items":[{"status":"completed"},{"status":"skipped"}]}
            self.assertTrue(fully_completed(complete))
            self.assertFalse(fully_completed(partial))
            save_cursor(td,1)
            self.assertEqual(read_cursor(td),1)
            save_cursor(td,2)
            self.assertEqual(read_cursor(td),2)
            (Path(td)/"agent-research-cursor.json").write_text('{"next_batch": 1000}',encoding="utf-8")
            with self.assertRaises(ValueError):
                read_cursor(td)

    def test_b_c_live_launcher_enables_rotation(self):
        code=(Path(__file__).resolve().parents[1]/"launch.py").read_text(encoding="utf-8")
        self.assertIn('agent_command.append("--auto-universe")',code)
        self.assertIn('"--hours", "6" if not args.demo else "24"',code)
        self.assertIn('if not args.demo:',code)

if __name__=="__main__":
    unittest.main()
