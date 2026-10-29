"""Read-only forward paper replay of immutable observation JSON files.

The replay is opt-in and bounded, and never uses historic research bars.
"""
import json
from pathlib import Path
from agent_forward_paper import simulate
from agent_forward_enrollment import _utc

MAX_OBSERVATIONS=3000
MAX_BYTES=4096

def replay(enrollment_path, observation_dir, interval_seconds=3600):
    ep=Path(enrollment_path)
    enrollment=json.loads(ep.read_text(encoding="utf-8"))
    if enrollment.get("schema")!="agent-forward-enrollment-v1" or enrollment.get("live_trading_authorized") is not False:
        raise ValueError("非法前向策略登記")
    root=Path(observation_dir)
    if not root.is_dir():
        return {"status":"waiting_future_candles","trades":0,"live_trading_authorized":False}
    paths=list(root.glob("*.json"))
    if len(paths)>MAX_OBSERVATIONS:
        raise ValueError("前向觀測資料量超過單次處理上限")
    found=[]
    for path in paths:
        if path.stat().st_size>MAX_BYTES:
            raise ValueError("觀測檔案過大")
        item=json.loads(path.read_text(encoding="utf-8"))
        if (item.get("symbol")==enrollment["symbol"] and
            item.get("research_sha256")==enrollment["research_sha256"]):
            if item.get("strategy")!=enrollment["strategy"]:
                raise ValueError("同來源策略不一致")
            if _utc(item["candle_time_utc"])<=_utc(enrollment["enrolled_at_utc"]):
                raise ValueError("觀測資料早於登記時刻")
            found.append(item)
    found.sort(key=lambda x:_utc(x["candle_time_utc"]))
    result=simulate(found,enrollment["strategy"],interval_seconds=interval_seconds)
    result["observation_source"]="immutable_post_enrollment_ledger"
    result["forward_status"]="hypothetical_not_realized"
    return result
