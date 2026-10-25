"""Opt-in, bounded forward observer of newly closed candles in local SQLite.

Does not create synthetic fills or fetch exchange APIs. Never modifies the
scanner's database. A missing bar must not be represented as observation.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sqlite3

from agent_forward_enrollment import _utc
from agent_forward_observations import record_candle

def observe_once(state_dir, *, max_enrollments=3, max_bars_each=5, now=None):
    if type(max_enrollments) is not int or not 1<=max_enrollments<=10:
        raise ValueError("策略數量超出上限")
    if type(max_bars_each) is not int or not 1<=max_bars_each<=20:
        raise ValueError("單次 K 棒處理超出上限")
    root=Path(state_dir)
    folder=root/"agent-forward"
    database=root/"research.sqlite3"
    stats={"status":"paper_only","checked":0,"observed":0,"skipped":0,
           "live_trading_authorized":False}
    if not folder.is_dir() or not database.is_file():
        return stats
    observed=_utc(now or datetime.now(timezone.utc).isoformat())
    files=sorted(folder.glob("*.json"))
    if len(files)>1000: raise ValueError("研究登記紀錄過多")
    with closing(sqlite3.connect(database.resolve().as_uri()+"?mode=ro",uri=True,timeout=5)) as db:
        for file in files[:max_enrollments]:
            stats["checked"]+=1
            try:
                if file.stat().st_size>8192: raise ValueError("登記檔案過大")
                enrollment=json.loads(file.read_text(encoding="utf-8"))
                if enrollment.get("schema")!="agent-forward-enrollment-v1" or enrollment.get("live_trading_authorized") is not False:
                    raise ValueError("非法策略登記")
                symbol=enrollment["symbol"]
                fingerprint=enrollment["research_sha256"]
                if not isinstance(fingerprint,str) or not fingerprint.isalnum() or len(fingerprint)>128:
                    raise ValueError("研究識別不合法")
                cutoff=max(_utc(enrollment["data_cutoff_utc"]),_utc(enrollment["enrolled_at_utc"]))
                folder_out=root/"agent-forward-observations"/fingerprint
                existing=list(folder_out.glob("*.json")) if folder_out.is_dir() else []
                if len(existing)>3000: raise ValueError("前向紀錄已達檢查上限")
                recorded_times=set()
                for prior in existing:
                    if prior.stat().st_size>4096: raise ValueError("前向觀測紀錄過大")
                    saved=json.loads(prior.read_text(encoding="utf-8"))
                    if saved.get("research_sha256")!=fingerprint or saved.get("symbol")!=symbol:
                        raise ValueError("前向紀錄來源不一致")
                    recorded_times.add(_utc(saved["candle_time_utc"]))
                # Advance beyond saved observations across bounded batches.
                if recorded_times:
                    ordered=sorted(recorded_times)
                    if any((b-a).total_seconds()!=3600 for a,b in zip(ordered,ordered[1:])):
                        raise ValueError("已保存前向 K 棒不連續，停止後續紀錄")
                    cutoff=max(cutoff,ordered[-1])
                query=db.execute("SELECT time,close_time,open,high,low,close,volume FROM candles "
                                 "WHERE symbol=? AND interval='1h' AND mode='live' AND time>? "
                                 "ORDER BY time ASC LIMIT ?",
                                 (symbol,cutoff.isoformat(),max_bars_each))
                expected_next=cutoff+timedelta(seconds=3600) if recorded_times else None
                for row in query.fetchall():
                    bar={"time":row[0],"close_time":row[1],"open":row[2],
                         "high":row[3],"low":row[4],"close":row[5],"volume":row[6]}
                    bar_time=_utc(bar["time"])
                    if expected_next is not None and bar_time!=expected_next:
                        raise ValueError("前向行情存在缺口，停止觀測")
                    if _utc(bar["close_time"])>=observed: break
                    record_candle(enrollment,bar,folder_out,observed_at=observed.isoformat())
                    stats["observed"]+=1
                    expected_next=bar_time+timedelta(seconds=3600)
            except (OSError,ValueError,TypeError,KeyError,RuntimeError,sqlite3.Error):
                stats["skipped"]+=1
    return stats

def main():
    parser=argparse.ArgumentParser(description="前向研究：讀取已收盤的本機 K 棒，無實盤權限")
    parser.add_argument("--state-dir",required=True)
    args=parser.parse_args()
    print(json.dumps(observe_once(args.state_dir),ensure_ascii=False))

if __name__=="__main__":
    main()
