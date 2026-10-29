"""Unified read-only status for the paper-forward research subsystem.

No repair, trading, exchange request or process management is performed.
"""
from agent_forward_freshness import assess_freshness
from agent_forward_lock_diagnostic import inspect_lock

def inspect_forward_health(state_dir, *, now=None):
    fresh=assess_freshness(state_dir,now=now)
    lock=inspect_lock(state_dir)
    if lock["state"] in ("requires_operator_review","invalid_lock_requires_review"):
        status="requires_operator_review"
        message="研究鎖定狀態異常，請確認程序後再處理；不自動解鎖"
    elif fresh["state"] in ("invalid","execution_stopped","stale"):
        status="requires_attention"
        message=fresh["message"]
    elif lock["state"]=="locked_or_running":
        status="running_or_locked"
        message="偵測到鎖定紀錄，不能單憑鎖定證明程序仍在執行"
    elif fresh["state"]=="not_started":
        status="not_started"
        message="前向研究尚無週期執行紀錄"
    else:
        status="recently_completed"
        message="近期有研究完成；不能據此證明行情、成交或獲利正常"
    return {"status":status,"message":message,"freshness":fresh["state"],
            "lock":lock["state"],"live_trading_authorized":False}
