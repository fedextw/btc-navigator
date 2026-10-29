"""Fair, paper-only head-to-head on candles unseen by both strategy searches."""
from datetime import datetime
from pathlib import Path
from agent_csv_research import COST, evaluate
from agent_research_cycle import CANDIDATES, make_signals
from agent_state_research import history_from_database

def _strategy(name):
    candidates={c[0]:c for c in CANDIDATES}
    if name in candidates:
        return candidates[name]
    if not isinstance(name,str):
        raise ValueError("策略名稱無效")
    parts=name.split("_")
    try:
        if len(parts)==3 and parts[0]=="trend":
            fast,slow=map(int,parts[1:])
            if 3<=fast<slow<=200 and name==f"trend_{fast}_{slow}":
                return (name,"trend",fast,slow)
        if len(parts)==2 and parts[0]=="breakout":
            window=int(parts[1])
            if 5<=window<=200 and name==f"breakout_{window}":
                return (name,"breakout",window,0)
    except ValueError:
        pass
    raise ValueError("策略候選不合法")

def compare_fresh_paper(state_dir, symbol, interval, old_strategy, new_strategy,
                        old_cutoff, new_cutoff, *, min_trades=30):
    from agent_symbol_validation import valid_symbol
    if not valid_symbol(symbol) or interval not in ("15m","1h","4h"):
        raise ValueError("研究標的不合法")
    old=_strategy(old_strategy)
    new=_strategy(new_strategy)
    def utc(value):
        if not isinstance(value,str):
            raise ValueError("缺少UTC時間")
        dt=datetime.fromisoformat(value.replace("Z","+00:00"))
        if dt.tzinfo is None or dt.utcoffset().total_seconds()!=0:
            raise ValueError("需使用UTC時間")
        return dt
    older=utc(old_cutoff)
    newer=utc(new_cutoff)
    if newer<=older or type(min_trades) is not int or min_trades<30:
        raise ValueError("前向比較區間或交易門檻無效")
    rows=history_from_database(Path(state_dir)/"research.sqlite3",symbol,interval,"live")
    bars=[(utc(r[0]),*r[1:]) for r in rows]
    start=next((i for i,b in enumerate(bars) if b[0]>newer),len(bars))
    result={"schema":"bc-fair-forward-comparison-v1","symbol":symbol,
            "interval":interval,"old_strategy":old_strategy,
            "new_strategy":new_strategy,"evaluation_after_utc":new_cutoff,
            "cost_fraction":COST,"paper_only":True,
            "independent_improvement_proven":False,
            "automatic_promotion_authorized":False,
            "live_trading_authorized":False}
    if start+4>=len(bars):
        return {**result,"status":"waiting_fresh_candles"}
    old_score=evaluate(bars,make_signals(bars,old),start,len(bars),COST)
    new_score=evaluate(bars,make_signals(bars,new),start,len(bars),COST)
    keys=("trades","net_expectancy_r","max_drawdown_pct","net_return_pct","profit_factor")
    result["old_metrics"]={k:old_score[k] for k in keys}
    result["new_metrics"]={k:new_score[k] for k in keys}
    if min(old_score["trades"],new_score["trades"])<min_trades:
        return {**result,"status":"insufficient_fresh_trades"}
    # A fresh comparison is descriptive, not a statistical significance or
    # deployment gate. Never promote either strategy from this result.
    result["status"]="fresh_paper_comparison_available"
    result["new_candidate_outperformed_in_sample"]=(
        new_score["net_expectancy_r"]>old_score["net_expectancy_r"]
        and new_score["net_return_pct"]>old_score["net_return_pct"]
        and new_score["max_drawdown_pct"]<=old_score["max_drawdown_pct"])
    return result
