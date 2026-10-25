"""Offline forward paper-fill estimator from immutable post-enrollment observations.

NO live order routing. Assumes hypothetical next-open entry and three-bar close
exit, not actual exchange fills. Fees/slippage are estimated; funding omitted.
"""
import math
from datetime import timedelta
from agent_forward_enrollment import _utc

def simulate(observations, strategy, interval_seconds=3600, round_trip_cost=0.0014):
    if not (isinstance(interval_seconds,int) and interval_seconds>0 and
            isinstance(round_trip_cost,(int,float)) and math.isfinite(round_trip_cost)
            and 0 <= round_trip_cost <= .1):
        raise ValueError("模擬設定不合法")
    from agent_research_cycle import CANDIDATES
    candidate=next((c for c in CANDIDATES if c[0]==strategy),None)
    if candidate is None:
        raise ValueError("未知或未登記的研究策略")
    if not observations:
        return {"status":"waiting_future_candles","trades":0,"net_return_pct":None,
                "cost_model":"fixed_round_trip_excludes_funding","live_trading_authorized":False}
    fingerprint=observations[0].get("research_sha256")
    symbol=observations[0].get("symbol")
    if not fingerprint or not symbol:
        raise ValueError("觀測紀錄缺少研究識別")
    bars=[]
    previous=None
    for item in observations:
        if (item.get("schema")!="agent-forward-observation-v1" or
            item.get("status")!="observed_not_traded" or
            item.get("live_trading_authorized") is not False or
            item.get("strategy")!=strategy or
            item.get("symbol")!=symbol or item.get("research_sha256")!=fingerprint):
            raise ValueError("不可混用不同策略、幣種或研究紀錄")
        t=_utc(item["candle_time_utc"])
        close_at=_utc(item["close_time_utc"])
        seen_at=_utc(item["observed_at_utc"])
        if close_at<=t or seen_at<=close_at:
            raise ValueError("含未確認收盤的行情")
        if previous is not None and (t-previous).total_seconds()!=interval_seconds:
            raise ValueError("前向行情有缺口或順序錯誤")
        previous=t
        values=item["ohlcv"]
        o,h,l,c,v=(float(values[k]) for k in ("open","high","low","close","volume"))
        if not all(math.isfinite(x) for x in (o,h,l,c,v)) or min(o,h,l,c)<=0 or v<0 or h<max(o,c,l) or l>min(o,c,h):
            raise ValueError("行情數值不合法")
        bars.append((t,o,h,l,c,v))
    # No historical research candles are mixed into paper observations. Require
    # enough new post-enrollment candles to establish indicators independently.
    from agent_research_cycle import make_signals
    sides=make_signals(bars,candidate)
    trades=[]
    i=80
    while i+3<len(bars):
        side=sides[i]
        if side:
            entry=bars[i+1][1]
            exit_price=bars[i+3][4]
            r=side*(exit_price/entry-1)-round_trip_cost
            trades.append({"signal_utc":bars[i][0].isoformat(),
                           "entry_utc":bars[i+1][0].isoformat(),
                           "exit_utc":bars[i+3][0].isoformat(),
                           "side":"LONG" if side>0 else "SHORT",
                           "net_return_fraction":round(r,10),
                           "fill_type":"hypothetical_next_open"})
            i+=3
        else:
            i+=1
    returns=[t["net_return_fraction"] for t in trades]
    wins=sum(v>0 for v in returns)
    gross_profit=sum(max(v,0) for v in returns)
    gross_loss=-sum(min(v,0) for v in returns)
    factor=(gross_profit/gross_loss if gross_loss>0 else None)
    equity=peak=1.0
    max_dd=0.0
    for trade in trades:
        equity*=1+trade["net_return_fraction"]
        peak=max(peak,equity)
        max_dd=max(max_dd,100*(1-equity/peak))
    return {"schema":"agent-forward-paper-v1","status":"paper_estimate_only",
            "symbol":symbol,"strategy":strategy,"research_sha256":fingerprint,
            "observed_bars":len(bars),"trades":len(trades),"trades_detail":trades,
            "net_return_pct":round(100*(equity-1),6),
            "max_drawdown_pct":round(max_dd,6),
            "win_rate_pct":round(100*wins/len(trades),4) if trades else None,
            "profit_factor":round(factor,6) if factor is not None else None,
            "net_expectancy_fraction":round(sum(returns)/len(returns),8) if trades else None,
            "evidence_status":"needs_more_forward_samples" if len(trades)<30 else "requires_independent_review",
            "cost_fraction_round_trip":round_trip_cost,
            "cost_model":"fixed_round_trip_excludes_funding",
            "not_actual_fills":True,"live_trading_authorized":False}
