"""Detect deterioration on genuinely newer paper evidence, not recycled holdout data.

A research candidate is never promoted or authorized for live trading.
"""
import math

def assess_forward_drift(reference, new, *, min_new_trades=30):
    if type(min_new_trades) is not int or min_new_trades<30:
        raise ValueError("新交易樣本門檻至少30筆")
    if not isinstance(reference,dict) or not isinstance(new,dict):
        raise ValueError("前向績效資料格式不符")
    end=reference.get("heldout_end_utc")
    start=new.get("first_signal_utc")
    if not isinstance(end,str) or not isinstance(start,str):
        raise ValueError("缺少歷史與前向資料時間")
    from datetime import datetime
    old=datetime.fromisoformat(end.replace("Z","+00:00"))
    fresh=datetime.fromisoformat(start.replace("Z","+00:00"))
    if old.tzinfo is None or fresh.tzinfo is None or fresh<=old:
        raise ValueError("前向資料必須嚴格晚於歷史測試")
    count=new.get("trades")
    expectancy=new.get("net_expectancy_r")
    drawdown=new.get("max_drawdown_pct")
    if (type(count) is not int or count<0 or
        type(expectancy) not in (int,float) or not math.isfinite(expectancy) or
        type(drawdown) not in (int,float) or not math.isfinite(drawdown) or drawdown<0):
        raise ValueError("前向績效值不合法")
    if new.get("costs_included") is not True or new.get("paper_only") is not True:
        raise ValueError("只接受包含交易成本的紙上績效")
    status=("insufficient_forward_evidence" if count<min_new_trades else
            "review_strategy_deterioration" if expectancy<=0 or drawdown>=12 else
            "continue_paper_observation")
    return {"schema":"bc-forward-drift-review-v1","status":status,
            "new_trades":count,"net_expectancy_r":expectancy,
            "max_drawdown_pct":drawdown,
            "paper_only":True,"automatic_promotion_authorized":False,
            "live_trading_authorized":False}
