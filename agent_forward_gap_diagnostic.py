"""Read-only diagnosis of missing 1h candles between saved forward observations.

No interpolated bars, no exchange requests, no repair mutations.
"""
import json
from datetime import timedelta
from pathlib import Path
from agent_forward_enrollment import _utc

def diagnose(state_dir, *, max_enrollments=10):
    if type(max_enrollments) is not int or not 1<=max_enrollments<=10:
        raise ValueError("超出檢查上限")
    root=Path(state_dir)
    folder=root/"agent-forward"
    if not folder.is_dir():
        return {"status":"not_started","gaps":[],"checked":0,"live_trading_authorized":False}
    files=sorted(folder.glob("*.json"))
    if len(files)>1000: raise ValueError("前向策略過多")
    gaps=[]
    checked=0
    for file in files[:max_enrollments]:
        checked+=1
        try:
            if file.stat().st_size>8192: raise ValueError("登記資料過大")
            entry=json.loads(file.read_text(encoding="utf-8"))
            if entry.get("schema")!="agent-forward-enrollment-v1" or entry.get("live_trading_authorized") is not False:
                raise ValueError("非法登記")
            fingerprint=entry["research_sha256"]
            if not isinstance(fingerprint,str) or not fingerprint.isalnum() or len(fingerprint)>128:
                raise ValueError("研究識別不合法")
            observations=root/"agent-forward-observations"/fingerprint
            prior=list(observations.glob("*.json")) if observations.is_dir() else []
            if len(prior)>3000: raise ValueError("觀測紀錄過多")
            times=[]
            for p in prior:
                if p.stat().st_size>4096: raise ValueError("觀測資料過大")
                value=json.loads(p.read_text(encoding="utf-8"))
                if value.get("research_sha256")!=fingerprint or value.get("symbol")!=entry["symbol"]:
                    raise ValueError("觀測來源不一致")
                times.append(_utc(value["candle_time_utc"]))
            times.sort()
            for a,b in zip(times,times[1:]):
                if (b-a).total_seconds()!=3600:
                    gaps.append({"symbol":entry["symbol"],"strategy":entry["strategy"],
                                 "expected_next_utc":(a+timedelta(hours=1)).isoformat(),
                                 "next_recorded_utc":b.isoformat(),"status":"missing_or_invalid_interval"})
        except (OSError,ValueError,TypeError,KeyError,RuntimeError):
            gaps.append({"symbol":"—","status":"invalid_evidence"})
    return {"status":"gaps_found" if gaps else "no_internal_gaps_detected",
            "checked":checked,"gaps":gaps[:30],
            "note":"只能檢查已保存觀測之間的缺口；無法證明最新行情已持續更新",
            "live_trading_authorized":False}
