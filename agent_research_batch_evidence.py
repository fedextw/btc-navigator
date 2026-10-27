"""Bounded append-only audit snapshots for multi-symbol paper research batches."""
import hashlib
import json
from pathlib import Path

def save_batch_evidence(state_dir, batch_number, report):
    if (type(batch_number) is not int or batch_number<0 or
        not isinstance(report,dict) or report.get("schema")!="agent-scheduler-v1" or
        report.get("paper_only") is not True or report.get("live_trading_authorized") is not False or
        not isinstance(report.get("items"),list) or len(report["items"])>10 or
        not isinstance(report.get("counts"),dict)):
        raise ValueError("批次研究證據無效")
    items=report["items"]
    if report["counts"].get("attempted")!=len(items):
        raise ValueError("研究筆數不一致")
    records=[]
    from agent_symbol_validation import valid_symbol
    for item in items:
        if not isinstance(item,dict) or not valid_symbol(item.get("symbol")) or item.get("status") not in ("completed","skipped"):
            raise ValueError("研究紀錄內容不合法")
        # Save provenance and outcome without secrets, API credentials or arbitrary output payloads.
        result=item.get("result") if isinstance(item.get("result"),dict) else {}
        records.append({"symbol":item["symbol"],"status":item["status"],
                        "error_type":item.get("error_type"),
                        "strategy_status":result.get("status"),
                        "selected_strategy":result.get("selected"),
                        "bars":result.get("bars"),
                        "backfill_status":(item.get("backfill") or {}).get("status")})
    payload={"schema":"agent-research-batch-evidence-v1","batch_number":batch_number,
             "finished_at":report.get("finished_at"),
             "counts":report["counts"],"items":records,
             "paper_only":True,"live_trading_authorized":False}
    serial=json.dumps(payload,ensure_ascii=False,sort_keys=True,allow_nan=False)+"\\n"
    sha=hashlib.sha256(serial.encode("utf-8")).hexdigest()
    folder=Path(state_dir)/"agent-research-batches"
    folder.mkdir(parents=True,exist_ok=True)
    dest=folder/(sha+".json")
    try:
        with dest.open("x",encoding="utf-8") as out:
            out.write(serial)
    except FileExistsError:
        if dest.read_text(encoding="utf-8")!=serial:
            raise RuntimeError("研究紀錄校驗失敗")
    return dest
