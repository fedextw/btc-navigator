"""Read-only assessment of fresh post-freeze candles for B+C paper candidates."""
import hashlib
import json
from datetime import datetime
from pathlib import Path
from agent_research_cycle import CANDIDATES, make_signals
from agent_csv_research import evaluate, COST
from agent_forward_drift import assess_forward_drift
from agent_state_research import history_from_database

def review_frozen_candidate(state_dir, frozen_path):
    state=Path(state_dir).resolve()
    folder=(state/"agent-frozen-paper-candidates").resolve()
    path=Path(frozen_path).resolve()
    if path.parent!=folder or not path.name.endswith(".json"):
        raise ValueError("前向基準位置不合法")
    raw=path.read_bytes()
    if len(raw)>4096 or hashlib.sha256(raw).hexdigest()!=path.stem:
        raise ValueError("前向基準完整性驗證失敗")
    candidate=json.loads(raw)
    if (candidate.get("schema")!="bc-frozen-paper-candidate-v1" or
        candidate.get("paper_only") is not True or
        candidate.get("live_trading_authorized") is not False or
        candidate.get("automatic_promotion_authorized") is not False):
        raise ValueError("前向基準權限無效")
    from agent_symbol_validation import valid_symbol
    symbol=candidate.get("symbol")
    interval=candidate.get("interval")
    strategy=candidate.get("strategy")
    if not valid_symbol(symbol) or interval not in ("15m","1h","4h"):
        raise ValueError("前向研究標的無效")
    # Accept only frozen, known strategy definitions; no arbitrary code execution.
    from agent_research_cycle import TREND_PAIRS, BREAKOUT_WINDOWS
    all_candidates={item[0]:item for item in CANDIDATES}
    if isinstance(strategy,str) and strategy not in all_candidates:
        parts=strategy.split("_")
        try:
            if len(parts)==3 and parts[0]=="trend":
                f,s=map(int,parts[1:])
                if not (3<=f<s<=200): raise ValueError()
                all_candidates[strategy]=(strategy,"trend",f,s)
            elif len(parts)==2 and parts[0]=="breakout":
                f=int(parts[1])
                if not 5<=f<=200: raise ValueError()
                all_candidates[strategy]=(strategy,"breakout",f,0)
        except ValueError:
            raise ValueError("策略參數無效") from None
    if strategy not in all_candidates:
        raise ValueError("不支援的策略候選")
    cutoff=candidate.get("historical_cutoff_utc")
    if not isinstance(cutoff,str): raise ValueError("缺少截止時間")
    cutoff_dt=datetime.fromisoformat(cutoff.replace("Z","+00:00"))
    if cutoff_dt.tzinfo is None: raise ValueError("時間必須包含時區")
    rows=history_from_database(state/"research.sqlite3",symbol,interval,"live")
    # History tuples are (ISO timestamp, open, high, low, close, volume).
    bars=[(datetime.fromisoformat(row[0].replace("Z","+00:00")),*row[1:]) for row in rows]
    start=next((i for i,row in enumerate(bars) if row[0]>cutoff_dt),len(bars))
    if start>=len(bars)-4:
        return {"schema":"bc-forward-observation-v1","status":"waiting_new_closed_candles",
                "paper_only":True,"live_trading_authorized":False}
    sides=make_signals(bars,all_candidates[strategy])
    # Start at or after the first post-cutoff signal; evaluate never enters
    # before start+1, and exits only at a subsequent fully closed candle.
    result=evaluate(bars,sides,start,len(bars),COST)
    details=result["trades_detail"]
    if not details:
        return {"schema":"bc-forward-observation-v1","status":"waiting_new_paper_trades",
                "paper_only":True,"live_trading_authorized":False}
    new={"first_signal_utc":details[0]["signal_time"],
         "trades":result["trades"],
         "net_expectancy_r":result["net_expectancy_r"],
         "max_drawdown_pct":result["max_drawdown_pct"],
         "costs_included":True,"paper_only":True}
    review=assess_forward_drift({"heldout_end_utc":cutoff},new)
    return {"schema":"bc-forward-observation-v1","symbol":symbol,
            "strategy":strategy,"reference_sha256":path.stem,
            "review":review,"paper_only":True,"live_trading_authorized":False,
            "automatic_promotion_authorized":False}
