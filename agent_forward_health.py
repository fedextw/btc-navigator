"""Bounded append-only run status journal for forward paper cycles."""
import json
from datetime import datetime,timezone
from pathlib import Path

def append_status(state_dir, record, *, stamp=None):
    root=Path(state_dir)/"agent-forward-health"
    if not isinstance(record,dict) or record.get("live_trading_authorized") is not False:
        raise ValueError("前向循環狀態不合法")
    root.mkdir(parents=True,exist_ok=True)
    at=stamp or datetime.now(timezone.utc).isoformat()
    from agent_forward_enrollment import _utc
    instant=_utc(at)
    name=instant.strftime("%Y%m%dT%H%M%S%fZ")
    data={"schema":"agent-forward-health-v1","timestamp_utc":instant.isoformat(),
          "status":str(record.get("status","unknown"))[:48],
          "cycles":len(record.get("cycles",[])),
          "live_trading_authorized":False}
    path=root/(name+".json")
    content=json.dumps(data,ensure_ascii=False,sort_keys=True)+"\n"
    with path.open("x",encoding="utf-8") as out:
        out.write(content)
    return path

def read_latest(state_dir):
    root=Path(state_dir)/"agent-forward-health"
    if not root.is_dir():
        return {"state":"not_started","message":"尚無前向定期研究紀錄"}
    files=sorted(root.glob("*.json"))
    if not files:
        return {"state":"not_started","message":"尚無前向定期研究紀錄"}
    latest=files[-1]
    if latest.stat().st_size>4096:
        return {"state":"invalid","message":"狀態檔案過大"}
    try:
        value=json.loads(latest.read_text(encoding="utf-8"))
        if value.get("schema")!="agent-forward-health-v1" or value.get("live_trading_authorized") is not False:
            raise ValueError("狀態格式不合法")
        return {"state":value["status"],"last_updated_utc":value["timestamp_utc"],
                "cycles":value["cycles"],"live_trading_authorized":False}
    except (OSError,ValueError,TypeError,KeyError):
        return {"state":"invalid","message":"健康紀錄無法讀取"}
