"""Bounded, read-only research data readiness summary for the UI."""
from contextlib import closing
from pathlib import Path
import sqlite3
from agent_research_universe import contiguous_utc, SECONDS
from agent_symbol_validation import valid_symbol

def summarize(state_dir, interval="1h", mode="live", inspect_limit=30):
    if interval not in SECONDS or mode not in ("live","demo") or not 1<=inspect_limit<=100:
        raise ValueError("研究資料摘要設定不正確")
    result={"database_exists":False,"observed_pairs":0,"enough_bars":0,
            "checked_pairs":0,"ready_in_checked":0,"ready_examples":[],
            "pending_examples":[],"note":"已檢查幣種為限；非所有合約皆已完成連續性檢查"}
    path=Path(state_dir)/"research.sqlite3"
    if not path.is_file(): return result
    result["database_exists"]=True
    try:
        with closing(sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
            rows=db.execute("SELECT symbol, COUNT(*) FROM candles WHERE interval=? AND mode=? "
                            "GROUP BY symbol ORDER BY symbol",(interval,mode)).fetchall()
            rows=[(symbol,count) for symbol,count in rows if valid_symbol(symbol)]
            result["observed_pairs"]=len(rows)
            eligible=[(symbol,count) for symbol,count in rows if count>=300]
            result["enough_bars"]=len(eligible)
            for symbol,count in eligible[:inspect_limit]:
                recent=db.execute("SELECT time FROM candles WHERE symbol=? AND interval=? AND mode=? "
                                  "ORDER BY time DESC LIMIT 300",(symbol,interval,mode)).fetchall()
                ready=contiguous_utc(recent,interval)
                result["checked_pairs"]+=1
                if ready:
                    result["ready_in_checked"]+=1
                    if len(result["ready_examples"])<8: result["ready_examples"].append(symbol)
                elif len(result["pending_examples"])<8:
                    result["pending_examples"].append(symbol)
    except sqlite3.Error:
        result["note"]="讀取資料庫失敗或結構未就緒，請查看掃描器日誌"
    return result
