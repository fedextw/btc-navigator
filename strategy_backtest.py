"""Fixed-rule historical replay. Never inserted into forward-learning tables."""
import hashlib
import pandas as pd
from strategy_rules import PROFILES,prepare,candidate,resample_higher
from strategy_execution import entry_fill,exit_on_bar,settle_values
from learning_lab import trade_stats
from market_data import INTERVALS


def run(candles,profile,symbol,mode='demo',fee_pct=.05,slippage_pct=.02,funding_pct_8h=.01):
    p=PROFILES[profile]
    if len(candles)<900 or not (candles.time.diff().dropna().dt.total_seconds()==INTERVALS[p['interval']]).all():
        raise ValueError('至少需要900根連續已收盤基準K線')
    if not 0<=fee_pct<=1 or not 0<=slippage_pct<=1 or not -1<=funding_pct_8h<=1:raise ValueError('成本參數不正確')
    prepared=prepare(candles,resample_higher(candles,p['higher']))
    active=None;pending=None;closed=[];cancelled=0
    for _,bar in prepared.iterrows():
        if pending:
            if profile=='intraday' and bar.time.tz_convert('Asia/Taipei').date()!=pd.Timestamp(pending['signal_time']).tz_convert('Asia/Taipei').date():
                pending=None;cancelled+=1
            else:
                entry=entry_fill(pending,bar,fee_pct,slippage_pct)
                if entry is None:pending=None;cancelled+=1
                else:
                    active={**pending,'entry':entry,'entry_time':str(bar.time),'fee_pct':fee_pct,'slippage_pct':slippage_pct,
                        'funding_pct_8h':funding_pct_8h,'quantity':1/entry,'bars_held':0,
                        'risk_budget':(abs(entry-pending['stop'])+(entry+pending['stop'])*fee_pct/100+pending['stop']*slippage_pct/100)/entry}
                    pending=None
        if active:
            active['bars_held']+=1
            outcome=exit_on_bar(active,bar)
            if outcome:
                raw,reason=outcome
                active.update(settle_values(active,raw,bar.time if 'gap' in reason else bar.close_time),exit_reason=reason,status='closed',source='historical_replay')
                closed.append(active);active=None
        if not active and not pending:
            plan=candidate(bar,profile,symbol,mode,fee_pct,slippage_pct)
            if plan['side']!='WAIT':pending=plan
    stats=trade_stats(closed)
    split=len(closed)*3//5
    return {'strategy':profile,'profile_version':p['version'],'symbol':symbol,'mode':mode,'created_at':str(pd.Timestamp.now(tz='UTC')),
        'dataset_sha256':hashlib.sha256(candles.to_csv(index=False).encode()).hexdigest(),
        'source':'historical_replay','stats':stats,'trades':closed,'early':trade_stats(closed[:split]),'later':trade_stats(closed[split:]),
        'open_or_pending':int(active is not None or pending is not None),'cancelled':cancelled,
        'assumptions':{'fee_pct':fee_pct,'slippage_pct':slippage_pct,'funding_pct_8h':funding_pct_8h},
        'limitations':['固定策略歷史重播，不是未來實績，不納入75%達標或AI訓練資料',
            '下一根開盤假設進場；未來紙上執行則等待保存預測之後的第一個尚未開始K線',
            '同根停損與止盈皆碰觸時先算停損，跳空停損按開盤不利成交，止盈跳空不給額外收益',
            '資金費採固定假設按時間估算，未含實際資金費、撮合、槓桿強平或組合資金限制']}
