"""Read-only recent closed-candle freshness check using research.sqlite3.

A recent local candle is not proof of live exchange connectivity or authentic
market data; this signal can only flag stale or missing local records.
"""
import sqlite3
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
from agent_forward_enrollment import _utc

def inspect_freshness(state_dir, *, now=None, max_age_seconds=10800, symbols=None):
    if type(max_age_seconds) is not int or not 3600<=max_age_seconds<=86400:
        raise ValueError("行情新鮮度上限不合法")
    current=_utc(now or datetime.now(timezone.utc).isoformat())
    if symbols is not None:
        if not isinstance(symbols,(list,tuple)) or not 1<=len(symbols)<=30 or any(
            not isinstance(x,str) or not x.endswith("USDT") or not x.isalnum() or len(x)>32
            for x in symbols) or len(set(symbols))!=len(symbols):
            raise ValueError("行情標的清單不合法")
    database=Path(state_dir)/"research.sqlite3"
    base={"status":"unverified","local_candle_recent":False,
          "exchange_connection_verified":False,"live_trading_authorized":False}
    if not database.is_file():
        return dict(base,reason="missing_database")
    try:
        with closing(sqlite3.connect(database.resolve().as_uri()+"?mode=ro",uri=True,timeout=5)) as db:
            if symbols is None:
                row=db.execute("SELECT MAX(close_time) FROM candles WHERE interval='1h' AND mode='live'").fetchone()
                rows=None
            else:
                rows=db.execute("SELECT symbol,MAX(close_time) FROM candles WHERE interval='1h' AND mode='live' AND symbol IN ("+
                                ",".join("?" for _ in symbols)+") GROUP BY symbol",symbols).fetchall()
                row=None
        if symbols is not None:
            known=dict(rows)
            details={}
            for symbol in symbols:
                raw=known.get(symbol)
                if not raw:
                    details[symbol]="missing"
                    continue
                age=(current-_utc(raw)).total_seconds()
                details[symbol]="future_or_unclosed" if age<0 else "recent" if age<=max_age_seconds else "stale"
            all_recent=all(v=="recent" for v in details.values())
            return dict(base,status="all_selected_recent" if all_recent else "selected_symbols_not_all_recent",
                        local_candle_recent=all_recent,symbol_freshness=details,checked_symbols=len(symbols))
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
