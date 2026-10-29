import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from agent_backup import backup_state
from agent_restore import restore_to_new_directory


class RestoreTests(unittest.TestCase):
    def test_round_trip_into_new_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); state=root/"state"; state.mkdir()
            with closing(sqlite3.connect(state/"research.sqlite3")) as db:
                db.execute("CREATE TABLE sample (value INTEGER)")
                db.execute("INSERT INTO sample VALUES (42)")
                db.commit()
            backup=root/"snapshot"
            backup_state(state,backup)
            result=restore_to_new_directory(backup,root/"restored")
            self.assertEqual(result["restored"],["research.sqlite3"])
            with closing(sqlite3.connect(root/"restored"/"research.sqlite3")) as db:
                self.assertEqual(db.execute("SELECT value FROM sample").fetchone()[0],42)

    def test_never_overwrite_existing_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); state=root/"state"; state.mkdir()
            with closing(sqlite3.connect(state/"research.sqlite3")) as db:
                db.execute("CREATE TABLE sample(a INTEGER)")
            backup=root/"snapshot"; backup_state(state,backup)
            (root/"existing").mkdir()
            with self.assertRaises(FileExistsError):
                restore_to_new_directory(backup,root/"existing")

    def test_corrupted_backup_rejected_before_creating_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);state=root/"state";state.mkdir()
            with closing(sqlite3.connect(state/"research.sqlite3")) as db:
                db.execute("CREATE TABLE sample(a INTEGER)")
            backup=root/"snapshot";backup_state(state,backup)
            with (backup/"research.sqlite3").open("ab") as output:
                output.write(b"corrupt")
            destination=root/"restored"
            with self.assertRaises(ValueError):
                restore_to_new_directory(backup,destination)
            self.assertFalse(destination.exists())


if __name__=="__main__":
    unittest.main()
