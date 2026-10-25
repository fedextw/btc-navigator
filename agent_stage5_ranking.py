"""Bounded, deterministic evidence ranking for stage-five paper candidates.

Ranking is a research triage aid, not automated strategy promotion or AI model
training. Only reviewed eligible paper candidates can be ranked.
"""
import math

def rank_candidates(candidates):
    if not isinstance(candidates,list) or len(candidates)>30:
        raise ValueError("策略候選清單不合法")
    ranked=[]
    for item in candidates:
        if not isinstance(item,dict) or not isinstance(item.get("decision"),dict):
            continue
        decision=item["decision"]
        if decision.get("status")!="eligible_for_manual_paper_review":
            continue
        stats=item.get("paper_evidence")
        if not isinstance(stats,dict):
            continue
        n=stats.get("prospective_eligible_trades")
        ret=stats.get("prospective_paper_net_return_pct")
        factor=stats.get("prospective_paper_profit_factor")
        dd=stats.get("prospective_paper_max_drawdown_pct")
        if (type(n) is not int or n<30 or
            any(type(v) not in (float,int) or not math.isfinite(v)
                for v in (ret,factor,dd)) or
            ret<=0 or factor<1.15 or dd<0 or dd>=12):
            continue
        ranked.append({"symbol":item["symbol"],"strategy":item["strategy"],
                       "research_sha256":item["research_sha256"],"samples":n,
                       "net_return_pct":ret,"profit_factor":factor,
                       "max_drawdown_pct":dd})
    # Prefer lower drawdown, then higher PF and return, with stable ties.
    ranked.sort(key=lambda x:(x["max_drawdown_pct"],-x["profit_factor"],
                               -x["net_return_pct"],-x["samples"],
                               x["symbol"],x["strategy"],x["research_sha256"]))
    return {"schema":"agent-stage5-ranking-v1",
            "ranking_method":"risk_first_research_triage_not_predictive_ai",
            "ranked":[dict(item,rank=i+1) for i,item in enumerate(ranked)],
            "automatic_promotion_authorized":False,
            "live_trading_authorized":False}
