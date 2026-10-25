"""Conservative profitability evidence gate for paper-only candidate research.

Passing means eligible for further forward testing, never real-order authorization.
"""
import math

def assess(stats, *, min_trades=20, min_profit_factor=1.15, max_drawdown_pct=12):
    if not isinstance(stats,dict):
        return {"eligible":False,"reasons":["缺少績效資料"],"live_trading_authorized":False}
    reasons=[]
    trades=stats.get("trades")
    expectancy=stats.get("net_expectancy_r")
    factor=stats.get("profit_factor")
    drawdown=stats.get("max_drawdown_pct")
    if type(trades) is not int or trades<min_trades:
        reasons.append("保留測試交易樣本不足")
    if not isinstance(expectancy,(float,int)) or not math.isfinite(expectancy) or expectancy<=0:
        reasons.append("扣除成本後期望報酬未達正值")
    if not isinstance(factor,(float,int)) or math.isnan(factor) or factor<min_profit_factor:
        reasons.append("保留測試獲利因子不足")
    if not isinstance(drawdown,(float,int)) or not math.isfinite(drawdown) or drawdown<0 or drawdown>=max_drawdown_pct:
        reasons.append("回撤超過研究門檻或資料異常")
    return {"eligible":not reasons,"reasons":reasons,"live_trading_authorized":False,
            "next_stage":"independent_forward_paper_test" if not reasons else "reject_or_collect_more"}
