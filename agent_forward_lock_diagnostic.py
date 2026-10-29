"""Read-only paper-forward lock inspection, never deletes or steals a lock."""
import json
import os
import time
from pathlib import Path

def inspect_lock(state_dir, *, now=None, stale_seconds=7200):
    if type(stale_seconds) is not int or not 300<=stale_seconds<=604800:
        raise ValueError("鎖定逾時門檻不合法")
    lock=Path(state_dir)/"agent-forward-pipeline.lock"
    if not lock.exists():
        return {"state":"unlocked","live_trading_authorized":False}
    try:
        if lock.stat().st_size>4096:
            raise ValueError("鎖定紀錄過大")
        data=json.loads(lock.read_text(encoding="utf-8"))
        if data.get("purpose")!="paper_forward_pipeline" or type(data.get("pid")) is not int or data["pid"]<=0:
            raise ValueError("鎖定內容不合法")
        age=max(0,int((time.time() if now is None else now)-lock.stat().st_mtime))
        # PID existence cannot reliably prove identity or ownership across restarts.
        state="requires_operator_review" if age>stale_seconds else "locked_or_running"
        return {"state":state,"age_seconds":age,"pid":data["pid"],
                "message":"不能僅憑 PID 或時間自動刪除鎖定；須人工確認沒有執行中的程序",
                "live_trading_authorized":False}
    except (OSError,ValueError,TypeError,KeyError,UnicodeError):
        return {"state":"invalid_lock_requires_review",
                "message":"鎖定檔損壞，需人工查核；不自動刪除",
                "live_trading_authorized":False}
