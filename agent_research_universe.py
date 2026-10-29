"""Select bounded, rotating batches of research-ready USDT contracts.

Read only the local research database; never make external API or order calls.
A symbol is eligible only when its most recent 300 candles are UTC and gap-free.
"""
from contextlib import closing
from datetime import datetime
from pathlib import Path
import sqlite3
from agent_symbol_validation import valid_symbol

SECONDS={"15m":900,"1h":3600,"4h":14400}

def contiguous_utc(timestamps, interval):
    if len(timestamps)<300:
        return False
    previous=None
    for stamp, in reversed(timestamps):
        try:
            current=datetime.fromisoformat(str(stamp).replace("Z","+00:00"))
        except (ValueError,TypeError):
            return False
        if current.tzinfo is None or current.utcoffset().total_seconds()!=0:
            return False
        if previous is not None and (current-previous).total_seconds()!=SECONDS[interval]:
            return False
        previous=current
    return True

def next_batch(state_dir, interval="1h", mode="live", limit=10, batch_number=0):
    if interval not in SECONDS or mode not in ("demo","live") or not 1<=limit<=10 or batch_number<0:
        raise ValueError("研究批次設定不正確")
    path=Path(state_dir)/"research.sqlite3"
    if not path.is_file():
        return ()
    try:
        with closing(sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True,timeout=5)) as db:
            rows=db.execute("SELECT symbol FROM candles WHERE interval=? AND mode=? "
                            "GROUP BY symbol HAVING COUNT(*) >= 300 ORDER BY symbol",
                            (interval,mode)).fetchall()
            ready=[]
            for (symbol,) in rows:
                if not valid_symbol(symbol):
                    continue
                recent=db.execute("SELECT time FROM candles WHERE symbol=? AND interval=? AND mode=? "
                                  "ORDER BY time DESC LIMIT 300",(symbol,interval,mode)).fetchall()
                if contiguous_utc(recent,interval):
                    ready.append(symbol)
    except sqlite3.OperationalError:
        return ()
    if not ready: return ()
    offset=(batch_number*limit)%len(ready)
    return tuple((ready+ready)[offset:offset+min(limit,len(ready))])
