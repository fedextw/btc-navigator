"""Read-only recent closed-candle freshness check using research.sqlite3.

A recent local candle is not proof of live exchange connectivity or authentic
market data; this signal can only flag stale or missing local records.
"""
import sqlite3
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
from agent_forward_enrollment import _utc

def inspect_freshness(state_dir, *, now=None, max_age_seconds=10800):
    if type(max_age_seconds) is not int or not 3600<=max_age_seconds<=86400:
        raise ValueError("行情新鮮度上限不合法")
    current=_utc(now or datetime.now(timezone.utc).isoformat())
    database=Path(state_dir)/"research.sqlite3"
    base={"status":"unverified","local_candle_recent":False,
          "exchange_connection_verified":False,"live_trading_authorized":False}
    if not database.is_file():
        return dict(base,reason="missing_database")
    try:
        with closing(sqlite3.connect(database.resolve().as_uri()+"?mode=ro",uri=True,timeout=5)) as db:
            row=db.execute("SELECT MAX(close_time) FROM candles WHERE interval='1h' AND mode='live'").fetchone()
        if not row or not row[0]:
            return dict(base,reason="missing_live_candles")
        newest=_utc(row[0])
        age=(current-newest).total_seconds()
        if age < 0:
            return dict(base,reason="future_or_unclosed_candle",last_close_utc=newest.isoformat())
        recent=age<=max_age_seconds
        return dict(base,status="recent_local_candle" if recent else "stale_local_candle",
                    local_candle_recent=recent,last_close_utc=newest.isoformat(),
                    seconds_since_last_close=int(age))
    except (OSError,sqlite3.Error,ValueError,TypeError):
        return dict(base,reason="invalid_candle_source")
