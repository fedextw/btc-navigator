"""Select a bounded rotating research batch from already-collected SQLite candles.

No network calls. Symbol listings alone do not count as research-ready data.
"""
from contextlib import closing
from pathlib import Path
import sqlite3
from agent_symbol_validation import valid_symbol

def next_batch(state_dir, interval="1h", mode="live", limit=10, batch_number=0):
    if interval not in ("15m","1h","4h") or mode not in ("demo","live") or not 1<=limit<=10 or batch_number<0:
        raise ValueError("研究批次設定不正確")
    path=Path(state_dir)/"research.sqlite3"
    if not path.is_file():
        return ()
    try:
        with closing(sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True,timeout=5)) as db:
            rows=db.execute(
                "SELECT symbol FROM candles WHERE interval=? AND mode=? "
                "GROUP BY symbol HAVING COUNT(*) >= 300 ORDER BY symbol",
                (interval,mode)).fetchall()
    except sqlite3.OperationalError:
        return ()
    universe=sorted({s for (s,) in rows if valid_symbol(s)})
    if not universe: return ()
    offset=(batch_number*limit)%len(universe)
    return tuple((universe+universe)[offset:offset+min(limit,len(universe))])
