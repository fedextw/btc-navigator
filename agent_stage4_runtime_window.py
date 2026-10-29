"""Read-only 72-hour journal evidence audit, not proof of process uptime."""
import json
from datetime import timedelta
from pathlib import Path
from agent_forward_enrollment import _utc

def inspect_window(state_dir, *, now, hours=72, max_gap_seconds=10800):
    if type(hours) is not int or not 24<=hours<=168:
        raise ValueError("觀察時數不合法")
    if type(max_gap_seconds) is not int or not 300<=max_gap_seconds<=86400:
        raise ValueError("間隔門檻不合法")
    end=_utc(now)
    start=end-timedelta(hours=hours)
    folder=Path(state_dir)/"agent-forward-health"
    paths=sorted(folder.glob("*.json")) if folder.is_dir() else []
    if len(paths)>20000:
        return {"status":"unverified","reason":"record_limit","live_trading_authorized":False}
    points=[]
    try:
        for p in paths:
            if p.stat().st_size>4096: raise ValueError("記錄過大")
            data=json.loads(p.read_text(encoding="utf-8"))
            if data.get("schema")!="agent-forward-health-v1" or data.get("live_trading_authorized") is not False:
                raise ValueError("紀錄無效")
            instant=_utc(data["timestamp_utc"])
            if start<=instant<=end: points.append((instant,data["status"]))
        points.sort()
        completed=all(s=="completed" for _,s in points)
        first_ok=bool(points) and (points[0][0]-start).total_seconds()<=max_gap_seconds
        last_ok=bool(points) and (end-points[-1][0]).total_seconds()<=max_gap_seconds
        gaps=sum((b[0]-a[0]).total_seconds()>max_gap_seconds for a,b in zip(points,points[1:]))
        enough=len(points)>=2 and first_ok and last_ok and completed and gaps==0
        return {"status":"journal_coverage" if enough else "insufficient_evidence",
                "hours":hours,"records":len(points),"failed_records":sum(s!="completed" for _,s in points),
                "gap_count":gaps,"covers_start":first_ok,"covers_end":last_ok,
                "journal_coverage_verified":enough,"verified_uninterrupted_uptime":False,
                "live_trading_authorized":False}
    except (OSError,ValueError,TypeError,KeyError,OverflowError):
        return {"status":"invalid_evidence","journal_coverage_verified":False,
                "verified_uninterrupted_uptime":False,"live_trading_authorized":False}
