"""Immutable paper-forward enrollment; future observations must be newer than enrollment.

This is an evidence ledger, not an execution engine. No exchange or broker access.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

def _utc(value):
    instant=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if instant.tzinfo is None or instant.utcoffset().total_seconds()!=0:
        raise ValueError("時間必須使用 UTC")
    return instant

def enroll(report, symbol, directory, enrolled_at=None):
    from agent_symbol_validation import valid_symbol
    if not valid_symbol(symbol) or report.get("schema")!="agent-cycle-v1":
        raise ValueError("研究來源不正確")
    if report.get("live_trading_authorized") is not False or report.get("paper_status")!="research_candidate":
        raise ValueError("策略尚未取得前向研究資格")
    if report.get("profitability_evidence",{}).get("eligible") is not True:
        raise ValueError("策略不符合獲利品質門檻")
    selected=report.get("selected")
    config=report.get("config",{})
    cutoff=_utc(config["heldout_end"])
    enrolled=_utc(enrolled_at or datetime.now(timezone.utc).isoformat())
    if enrolled<=cutoff:
        raise ValueError("前向測試起點不能早於研究資料截止時間")
    source=json.dumps(report,sort_keys=True,ensure_ascii=False,allow_nan=False)
    fingerprint=hashlib.sha256(source.encode("utf-8")).hexdigest()
    item={"schema":"agent-forward-enrollment-v1","symbol":symbol,"strategy":selected,
          "research_sha256":fingerprint,"data_cutoff_utc":cutoff.isoformat(),
          "enrolled_at_utc":enrolled.isoformat(),"status":"awaiting_future_candles",
          "observed_trades":0,"live_trading_authorized":False}
    folder=Path(directory);folder.mkdir(parents=True,exist_ok=True)
    identity=hashlib.sha256(json.dumps(item,sort_keys=True).encode()).hexdigest()
    path=folder/(identity+".json")
    data=json.dumps(item,ensure_ascii=False,sort_keys=True,indent=2)+"\n"
    try:
        with path.open("x",encoding="utf-8") as f:f.write(data)
    except FileExistsError:
        if path.read_text(encoding="utf-8")!=data:
            raise RuntimeError("前向紀錄衝突")
    return path

def eligible_future_candle(enrollment, candle_time):
    cutoff=_utc(enrollment["data_cutoff_utc"])
    start=_utc(enrollment["enrolled_at_utc"])
    return _utc(candle_time)>max(cutoff,start)
