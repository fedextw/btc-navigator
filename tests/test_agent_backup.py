import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from agent_backup import backup_state, verify_backup


class BackupTests(unittest.TestCase):
    def test_backup_and_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=Path(tmp)/"state";state.mkdir()
            with closing(sqlite3.connect(state/"research.sqlite3")) as db:
                db.execute("CREATE TABLE example (id INTEGER PRIMARY KEY, value TEXT)")
                db.execute("INSERT INTO example(value) VALUES ('test')")
                db.commit()
            destination=Path(tmp)/"backup"
            report=backup_state(state,destination)
            self.assertEqual(len(report["files"]),1)
            self.assertTrue(verify_backup(destination))
            with closing(sqlite3.connect(destination/"research.sqlite3")) as db:
                self.assertEqual(db.execute("SELECT value FROM example").fetchone()[0],"test")

    def test_reject_backup_into_state_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=Path(tmp)/"state";state.mkdir()
            with self.assertRaises(ValueError):
                backup_state(state,state/"backup")

    def test_reject_tampered_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=Path(tmp)/"state";state.mkdir()
            with closing(sqlite3.connect(state/"research.sqlite3")) as db:
                db.execute("CREATE TABLE foo(a INTEGER)")
            destination=Path(tmp)/"backup"
            backup_state(state,destination)
            with (destination/"research.sqlite3").open("ab") as f:
                f.write(b"tamper")
            with self.assertRaises(ValueError):
                verify_backup(destination)


if __name__=="__main__":
    unittest.main()
