"""Durable cursor for bounded multi-symbol paper research. No order permissions."""
import json
import os
import tempfile
from pathlib import Path

def read_cursor(state_dir):
    path=Path(state_dir)/"agent-research-cursor.json"
    if not path.is_file():
        return 0
    if path.stat().st_size>2048:
        raise ValueError("研究進度檔過大")
    data=json.loads(path.read_text(encoding="utf-8"))
    if (data.get("schema")!="agent-research-cursor-v1" or
        type(data.get("next_batch")) is not int or data["next_batch"]<0 or
        data.get("live_trading_authorized") is not False):
        raise ValueError("研究進度檔無效")
    return data["next_batch"]

def save_cursor(state_dir, number):
    if type(number) is not int or number<0:
        raise ValueError("研究進度不合法")
    folder=Path(state_dir)
    folder.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile("w",dir=folder,encoding="utf-8",
                                     suffix=".tmp",delete=False) as out:
        json.dump({"schema":"agent-research-cursor-v1","next_batch":number,
                   "live_trading_authorized":False},out)
        temp=out.name
    os.replace(temp,folder/"agent-research-cursor.json")

def fully_completed(report):
    items=report.get("items")
    counts=report.get("counts")
    return (isinstance(items,list) and len(items)>0 and isinstance(counts,dict)
            and type(counts.get("attempted")) is int
            and counts["attempted"]==len(items)
            and type(counts.get("completed")) is int
            and counts["completed"]==len(items)
            and all(isinstance(x,dict) and x.get("status")=="completed" for x in items))
