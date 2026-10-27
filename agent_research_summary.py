"""Read and summarize immutable multi-symbol research outcomes, never rank by unverified PnL."""
import hashlib
import json
from pathlib import Path
from agent_symbol_validation import valid_symbol

def summarize_batches(state_dir, limit=200):
    if type(limit) is not int or not 1<=limit<=500:
        raise ValueError("研究紀錄讀取上限不合法")
    folder=Path(state_dir)/"agent-research-batches"
    files=sorted(folder.glob("*.json")) if folder.is_dir() else []
    if len(files)>5000:
        raise ValueError("研究紀錄過多，停止彙整")
    outcomes={}
    rejected=0
    attempts=0
    for path in files[-limit:]:
        if path.stat().st_size>32768:
            raise ValueError("研究紀錄檔異常")
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=path.stem:
            raise ValueError("研究紀錄指紋不符")
        data=json.loads(raw)
        if (data.get("schema")!="agent-research-batch-evidence-v1"
            or data.get("paper_only") is not True
            or data.get("live_trading_authorized") is not False):
            raise ValueError("研究紀錄權限或格式無效")
        items=data.get("items")
        if not isinstance(items,list) or len(items)>10:
            raise ValueError("研究紀錄內容異常")
        for item in items:
            if not isinstance(item,dict) or not valid_symbol(item.get("symbol")) or item.get("status") not in ("completed","skipped"):
                raise ValueError("研究幣種或狀態異常")
            symbol=item["symbol"]
            record=outcomes.setdefault(symbol,{"completed":0,"skipped":0})
            record[item["status"]]+=1
            attempts+=1
            if item["status"]=="completed" and item.get("strategy_status")=="rejected":
                rejected+=1
    return {"schema":"agent-multi-symbol-research-summary-v1",
            "files_checked":min(len(files),limit),"symbols_observed":len(outcomes),
            "total_attempts":attempts,"rejected_research":rejected,
            "by_symbol":dict(sorted(outcomes.items())),
            "evidence_type":"research_outcome_only_not_prospective_performance",
            "automatic_promotion_authorized":False,"live_trading_authorized":False}
