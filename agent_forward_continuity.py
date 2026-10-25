"""Read-only continuity report for bounded forward research health journal.

A span of successful journal timestamps is not proof of uninterrupted process
uptime; this report explicitly distinguishes recorded attempts from uptime.
"""
import json
from datetime import datetime,timezone
from pathlib import Path
from agent_forward_enrollment import _utc

def summarize_continuity(state_dir, *, max_records=500, max_gap_seconds=10800):
    if type(max_records) is not int or not 2<=max_records<=2000:
        raise ValueError("記錄檢查上限不合法")
    if type(max_gap_seconds) is not int or not 300<=max_gap_seconds<=604800:
        raise ValueError("間隔上限不合法")
    folder=Path(state_dir)/"agent-forward-health"
    paths=sorted(folder.glob("*.json")) if folder.is_dir() else []
    if len(paths)>20000:
        return {"status":"unverified","reason":"too_many_records","live_trading_authorized":False}
    points=[]
    try:
        for path in paths[-max_records:]:
            if path.stat().st_size>4096: raise ValueError("健康紀錄過大")
            data=json.loads(path.read_text(encoding="utf-8"))
            if data.get("schema")!="agent-forward-health-v1" or data.get("live_trading_authorized") is not False:
                raise ValueError("健康紀錄來源不合法")
            points.append((_utc(data["timestamp_utc"]),data["status"]))
        points.sort()
        gaps=[{"start_utc":a[0].isoformat(),"end_utc":b[0].isoformat(),
               "seconds":int((b[0]-a[0]).total_seconds())}
              for a,b in zip(points,points[1:]) if (b[0]-a[0]).total_seconds()>max_gap_seconds]
        failures=sum(status!="completed" for _,status in points)
        return {"status":"recorded_history_only" if len(points)>=2 and failures==0 and not gaps else "insufficient_or_interrupted",
                "records":len(points),"failed_records":failures,"gaps":gaps[:30],
                "first_utc":points[0][0].isoformat() if points else None,
                "last_utc":points[-1][0].isoformat() if points else None,
                "verified_uninterrupted_uptime":False,
                "live_trading_authorized":False}
    except (OSError,ValueError,TypeError,KeyError,OverflowError):
        return {"status":"invalid_evidence","verified_uninterrupted_uptime":False,
                "live_trading_authorized":False}
