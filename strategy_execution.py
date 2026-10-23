"""Conservative OHLC execution shared by historical and forward strategy research."""
import math
import pandas as pd
from market_data import INTERVALS


def eligible_time(signal_time,observed_at,interval):
    # No pretending to fill an open that occurred before the forecast was saved.
    after=max(pd.Timestamp(signal_time),pd.Timestamp(observed_at))+pd.Timedelta(nanoseconds=1)
    return after.ceil(f'{INTERVALS[interval]}s')


def entry_fill(plan,bar,fee_pct,slip_pct):
    direction=1 if plan['side']=='LONG' else -1
    raw=float(bar.open)
    if abs(raw-plan['reference'])>.75*plan['atr'] or direction*(raw-plan['stop'])<=0 or direction*(plan['target']-raw)<=0:
        return None
    price=raw*(1+direction*slip_pct/100)
    if direction*(price-plan['stop'])<=0 or direction*(plan['target']-price)<=0:
        return None
    return price


def exit_on_bar(trade,bar):
    long=trade['side']=='LONG';stop,target=trade['stop'],trade['target']
    if (long and bar.open<=stop) or (not long and bar.open>=stop):return float(bar.open),'stop_gap'
    if (long and bar.open>=target) or (not long and bar.open<=target):return float(target),'target_gap_conservative'
    stopped=bar.low<=stop if long else bar.high>=stop
    targeted=bar.high>=target if long else bar.low<=target
    if stopped:return float(stop),'stop_both_hit' if targeted else 'stop'
    if targeted:return float(target),'target'
    if trade['strategy']=='intraday':
        next_date=(bar.close_time+pd.Timedelta(milliseconds=1)).tz_convert('Asia/Taipei').date()
        entry_date=pd.Timestamp(trade['entry_time']).tz_convert('Asia/Taipei').date()
        if next_date!=entry_date:return float(bar.close),'session_close'
    if trade['bars_held']>=trade['max_bars']:return float(bar.close),'time_limit'
    return None


def settle_values(trade,raw_exit,exit_time):
    direction=1 if trade['side']=='LONG' else -1
    exit_price=raw_exit*(1-direction*trade['slippage_pct']/100)
    quantity=trade.get('quantity',1/trade['entry'])
    gross=direction*quantity*(exit_price-trade['entry'])
    fees=quantity*(trade['entry']+exit_price)*trade['fee_pct']/100
    hours=max(0,(pd.Timestamp(exit_time)-pd.Timestamp(trade['entry_time'])).total_seconds()/3600)
    funding=direction*quantity*trade['entry']*trade.get('funding_pct_8h',.01)/100*hours/8
    pnl=gross-fees-funding
    nominal=quantity*trade['entry']
    return {'exit':exit_price,'exit_time':str(exit_time),'gross_pnl':gross,'fees':fees,'funding':funding,
            'pnl':pnl,'net_return':pnl/nominal,'net_r':pnl/trade['risk_budget'] if trade.get('risk_budget',0)>0 else None}
