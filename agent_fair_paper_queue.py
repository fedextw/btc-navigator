"""Append-only B+C paper comparison records and bounded fair forward reviews."""
import hashlib
import json
from pathlib import Path

def save_comparison_request(state_dir, symbol, interval, comparison):
    if not isinstance(comparison,dict) or comparison.get("status")!="awaiting_fresh_independent_comparison":
        return None
    if comparison.get("live_trading_authorized") is not False:
        raise ValueError("禁止使用可實盤比較請求")
    from agent_symbol_validation import valid_symbol
    if not valid_symbol(symbol) or interval not in ("15m","1h","4h"):
        raise ValueError("比較標的或週期無效")
    keys=("old_strategy","new_candidate","old_historical_cutoff_utc","new_research_cutoff_utc")
    if any(not isinstance(comparison.get(k),str) or not comparison[k] for k in keys):
        raise ValueError("缺少經驗證的策略及時間界線")
    record={"schema":"bc-fair-paper-request-v1","symbol":symbol,"interval":interval,
            "old_strategy":comparison["old_strategy"],
            "new_strategy":comparison["new_candidate"],
            "old_cutoff":comparison["old_historical_cutoff_utc"],
            "new_cutoff":comparison["new_research_cutoff_utc"],
            "paper_only":True,"live_trading_authorized":False}
    raw=json.dumps(record,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()
    folder=Path(state_dir)/"agent-paper-comparison-requests"
    folder.mkdir(parents=True,exist_ok=True)
    key=hashlib.sha256(raw).hexdigest()
    target=folder/(key+".json")
    try:
        with target.open("xb") as file:
            file.write(raw)
    except FileExistsError:
        if target.read_bytes()!=raw:
            raise ValueError("比較請求指紋不符")
    return {"status":"awaiting_fresh_forward_candles","request_sha256":key,
            "live_trading_authorized":False}

def review_comparison_requests(state_dir, *, limit=2, batch_number=0):
    if type(limit) is not int or not 1<=limit<=5 or type(batch_number) is not int or batch_number<0:
        raise ValueError("比較排程參數無效")
    folder=Path(state_dir)/"agent-paper-comparison-requests"
    files=sorted(folder.glob("*.json")) if folder.is_dir() else []
    offset=(batch_number*limit)%len(files) if files else 0
    selected=(files+files)[offset:offset+min(limit,len(files))]
    items=[]
    from agent_fair_forward_comparison import compare_fresh_paper
    for path in selected:
        try:
            raw=path.read_bytes()
            if len(raw)>4096 or hashlib.sha256(raw).hexdigest()!=path.stem:
                raise ValueError("比較請求指紋錯誤")
            record=json.loads(raw)
            if record.get("schema")!="bc-fair-paper-request-v1" or record.get("paper_only") is not True or record.get("live_trading_authorized") is not False:
                raise ValueError("比較權限或格式錯誤")
            result=compare_fresh_paper(
                state_dir,record["symbol"],record["interval"],
                record["old_strategy"],record["new_strategy"],
                record["old_cutoff"],record["new_cutoff"])
            if result.get("live_trading_authorized") is not False:
                raise ValueError("比較結果權限異常")
            items.append({"request_sha256":path.stem,"status":result["status"],
                          "result":result,"live_trading_authorized":False})
        except (ValueError,OSError,TypeError,KeyError) as exc:
            items.append({"request_sha256":path.stem,"status":"review_error",
                          "error_type":type(exc).__name__,"live_trading_authorized":False})
    return {"schema":"bc-fair-paper-batch-v1","total_requests":len(files),
            "reviewed":len(items),"items":items,"paper_only":True,
            "automatic_promotion_authorized":False,"live_trading_authorized":False}
