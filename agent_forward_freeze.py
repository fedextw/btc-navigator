"""Freeze research candidates before any later paper observation.

Recording eligibility is not strategy promotion or execution authorization.
"""
import hashlib
import json
from pathlib import Path

def freeze_candidate(state_dir, research):
    if not isinstance(research,dict) or research.get("status")!="research_candidate":
        return None
    source=research.get("source")
    selected=research.get("selected")
    if (not isinstance(source,dict) or not isinstance(selected,str) or
        not selected or not isinstance(research.get("report_path"),str) or
        research.get("live_trading_authorized") is not False):
        raise ValueError("研究候選證據不足，拒絕建立前向基準")
    from agent_symbol_validation import valid_symbol
    if not valid_symbol(source.get("symbol")) or source.get("mode")!="live":
        return None
    report_path=Path(research["report_path"])
    record=json.loads(report_path.read_text(encoding="utf-8"))
    cutoff=record.get("config",{}).get("heldout_end")
    digest=record.get("dataset_sha256")
    if not isinstance(cutoff,str) or not isinstance(digest,str) or len(digest)!=64:
        raise ValueError("缺少研究時間界線或資料指紋")
    frozen={"schema":"bc-frozen-paper-candidate-v1","symbol":source["symbol"],
            "interval":source["interval"],"strategy":selected,
            "historical_cutoff_utc":cutoff,"dataset_sha256":digest,
            "reference_report_sha256":hashlib.sha256(report_path.read_bytes()).hexdigest(),
            "paper_only":True,"automatic_promotion_authorized":False,
            "live_trading_authorized":False}
    raw=json.dumps(frozen,ensure_ascii=False,sort_keys=True,allow_nan=False).encode("utf-8")
    key=hashlib.sha256(raw).hexdigest()
    folder=Path(state_dir)/"agent-frozen-paper-candidates"
    folder.mkdir(parents=True,exist_ok=True)
    target=folder/(key+".json")
    try:
        with target.open("xb") as output:
            output.write(raw)
    except FileExistsError:
        if target.read_bytes()!=raw:
            raise ValueError("前向基準指紋不符")
    return {"status":"frozen_for_future_paper_review",
            "reference_sha256":key,"historical_cutoff_utc":cutoff,
            "live_trading_authorized":False}
