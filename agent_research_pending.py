"""Persist skipped symbols for a single bounded batch, no live permissions."""
import json
import os
import tempfile
from pathlib import Path
from agent_symbol_validation import valid_symbol

def load_pending(state_dir,batch_number):
    path=Path(state_dir)/"agent-research-pending.json"
    if not path.exists():
        return ()
    if path.stat().st_size>2048:
        raise ValueError("未完成研究紀錄過大")
    data=json.loads(path.read_text(encoding="utf-8"))
    symbols=data.get("symbols")
    if (data.get("schema")!="agent-research-pending-v1"
        or data.get("live_trading_authorized") is not False
        or type(data.get("batch_number")) is not int
        or data["batch_number"]!=batch_number
        or not isinstance(symbols,list) or not 1<=len(symbols)<=10
        or len(set(symbols))!=len(symbols)
        or not all(valid_symbol(s) for s in symbols)):
        raise ValueError("未完成研究紀錄不符合目前批次")
    return tuple(symbols)

def save_pending(state_dir,batch_number,symbols):
    if (type(batch_number) is not int or batch_number<0
        or not 1<=len(symbols)<=10 or len(set(symbols))!=len(symbols)
        or not all(valid_symbol(s) for s in symbols)):
        raise ValueError("未完成研究參數不合法")
    root=Path(state_dir)
    root.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile("w",dir=root,encoding="utf-8",suffix=".tmp",delete=False) as out:
        json.dump({"schema":"agent-research-pending-v1","batch_number":batch_number,
                   "symbols":list(symbols),"live_trading_authorized":False},out)
        temporary=out.name
    os.replace(temporary,root/"agent-research-pending.json")

def clear_pending(state_dir):
    (Path(state_dir)/"agent-research-pending.json").unlink(missing_ok=True)
