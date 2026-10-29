"""Read-only freshness assessment of bounded forward cycle health journal."""
from datetime import datetime, timezone
from agent_forward_enrollment import _utc
from agent_forward_health import read_latest

def assess_freshness(state_dir, *, now=None, stale_after_seconds=10800):
    if type(stale_after_seconds) is not int or not 300<=stale_after_seconds<=604800:
        raise ValueError("健康檢查時限不合法")
    current=_utc(now or datetime.now(timezone.utc).isoformat())
    latest=read_latest(state_dir)
    state=latest.get("state")
    if state in ("not_started","invalid"):
        return {"state":state,"message":latest.get("message","尚無有效資料"),
                "live_trading_authorized":False}
    try:
        updated=_utc(latest["last_updated_utc"])
        age=(current-updated).total_seconds()
        if age < -60: raise ValueError("狀態時間晚於現在")
        if state!="completed":
            label="execution_stopped"
            message="最近一輪研究未完整完成，請檢查日誌"
        elif age>stale_after_seconds:
            label="stale"
            message="前向研究太久沒有更新，應檢查排程是否仍在運作"
        else:
            label="recently_completed"
            message="最近有完成研究；不代表新行情、成交或獲利正常"
        return {"state":label,"last_updated_utc":updated.isoformat(),
                "seconds_since_update":max(0,int(age)),
                "message":message,"live_trading_authorized":False}
    except (KeyError,ValueError,TypeError,OverflowError):
        return {"state":"invalid","message":"更新時間異常，無法確認研究健康",
                "live_trading_authorized":False}
