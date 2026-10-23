"""Initialize WAL databases safely when UI and background threads start together."""
from pathlib import Path
import sqlite3
import threading
import time

_initialization = threading.Lock()


def open_database(path, schema, rows=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _initialization:
        for attempt in range(5):
            db = sqlite3.connect(path, timeout=20)
            try:
                db.execute("PRAGMA busy_timeout=20000")
                if db.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
                    db.execute("PRAGMA journal_mode=WAL")
                db.executescript(schema)
                if rows:
                    db.row_factory = sqlite3.Row
                return db
            except sqlite3.OperationalError as exc:
                db.close()
                if "locked" not in str(exc).lower() or attempt == 4:
                    raise
                time.sleep(.05 * (attempt + 1))
