"""Two independent paper accounts. Forecasts are immutable before future fills.

No exchange account access. Unknown paths freeze reserved capital, never invent P&L.
"""
from datetime import datetime,timezone
import json
from pathlib import Path
import pandas as pd

from runtime_config import STATE_ROOT
from sqlite_support import open_database
from strategy_rules import PROFILES,prepare,candidate
from strategy_execution import eligible_time,entry_fill,exit_on_bar,settle_values
from market_data import INTERVALS

DEFAULT_RISK={'initial':10000.,'risk_pct':.5,'max_positions':5,'allocation_pct':20.,'daily_loss_pct':2.,
              'fee_pct':.05,'slippage_pct':.02,'funding_pct_8h':.01}


def connect(root=STATE_ROOT):
    Path(root).mkdir(parents=True,exist_ok=True)
    return open_database(Path(root)/'strategies.sqlite3', '''
      CREATE TABLE IF NOT EXISTS strategy_state(name TEXT PRIMARY KEY,payload TEXT);
      CREATE TABLE IF NOT EXISTS strategy_accounts(strategy TEXT,mode TEXT,payload TEXT,PRIMARY KEY(strategy,mode));
      CREATE TABLE IF NOT EXISTS strategy_latest(strategy TEXT,symbol TEXT,mode TEXT,payload TEXT,PRIMARY KEY(strategy,symbol,mode));
      CREATE TABLE IF NOT EXISTS strategy_trades(id TEXT PRIMARY KEY,strategy TEXT,symbol TEXT,mode TEXT,status TEXT,signal_time TEXT,payload TEXT);
      CREATE INDEX IF NOT EXISTS strategy_status ON strategy_trades(strategy,mode,status);
      CREATE TABLE IF NOT EXISTS strategy_equity(id INTEGER PRIMARY KEY AUTOINCREMENT,strategy TEXT,mode TEXT,observed_at TEXT,equity REAL,reason TEXT);
      CREATE TABLE IF NOT EXISTS strategy_ai_inputs(trade_id TEXT PRIMARY KEY,requested_at TEXT,provider TEXT,model TEXT,payload TEXT);
      CREATE TABLE IF NOT EXISTS strategy_models(id TEXT PRIMARY KEY,profile TEXT,mode TEXT,created_at TEXT,payload TEXT);
      CREATE TABLE IF NOT EXISTS strategy_training_runs(id INTEGER PRIMARY KEY AUTOINCREMENT,profile TEXT,mode TEXT,attempted_at TEXT,source_count INTEGER,result TEXT,model_id TEXT);
      CREATE TABLE IF NOT EXISTS strategy_reviews(id TEXT PRIMARY KEY,strategy TEXT,mode TEXT,observed_at TEXT,payload TEXT);
    ''',rows=True)


def dumps(value):return json.dumps(value,ensure_ascii=False,allow_nan=False)


def state(db,name,value=None):
    if value is not None:
        db.execute('INSERT OR REPLACE INTO strategy_state VALUES (?,?)',(name,dumps(value)));db.commit();return value
    row=db.execute('SELECT payload FROM strategy_state WHERE name=?',(name,)).fetchone()
    return json.loads(row[0]) if row else {}


def save_trade(db,t):
    db.execute('INSERT OR REPLACE INTO strategy_trades VALUES (?,?,?,?,?,?,?)',(t['id'],t['strategy'],t['symbol'],t['mode'],t['status'],t['signal_time'],dumps(t)))


def save_account(db,a):
    db.execute('INSERT OR REPLACE INTO strategy_accounts VALUES (?,?,?)',(a['strategy'],a['mode'],dumps(a)))


def account(db,strategy,mode,risk,now):
    row=db.execute('SELECT payload FROM strategy_accounts WHERE strategy=? AND mode=?',(strategy,mode)).fetchone()
    day=pd.Timestamp(now).tz_convert('Asia/Taipei').strftime('%Y-%m-%d')
    a=json.loads(row[0]) if row else {'strategy':strategy,'mode':mode,'initial':risk['initial'],'equity':risk['initial'],
        'peak':risk['initial'],'max_drawdown_pct':0.,'day':day,'day_start':risk['initial'],'created_at':str(now)}
    if a['day']!=day:a.update(day=day,day_start=a['equity'])
    return a


def equity_event(db,a,now,reason):
    a['peak']=max(a['peak'],a['equity'])
    a['max_drawdown_pct']=max(a['max_drawdown_pct'],(a['peak']-a['equity'])/a['peak']*100)
    db.execute('INSERT INTO strategy_equity(strategy,mode,observed_at,equity,reason) VALUES (?,?,?,?,?)',(a['strategy'],a['mode'],str(now),a['equity'],reason))


def process(db,candles,higher,profile,symbol,mode,risk=None,now=None,context=None,allow_new=True,quote_context=None,funding_context=None):
    risk={**DEFAULT_RISK,**(risk or {})}
    now=pd.Timestamp(now or datetime.now(timezone.utc))
    p=PROFILES[profile]; interval=p['interval']; seconds=INTERVALS[interval]
    frame=candles[candles.close_time<=now].copy()
    if len(frame)<200 or not (frame.time.diff().dropna().dt.total_seconds()==seconds).all():
        with db:
            for row in db.execute("SELECT payload FROM strategy_trades WHERE strategy=? AND symbol=? AND mode=? AND status IN ('pending','open')",(profile,symbol,mode)).fetchall():
                trade=json.loads(row[0]);trade.update(status='unresolved',reason='基準行情不足或有缺口，資金保留待還原');save_trade(db,trade)
        raise ValueError('策略基準行情不足或有缺口，停止新研究')
    h=higher[higher.close_time<=frame.iloc[-1].close_time].copy()
    if len(h)<200 or not (h.time.diff().dropna().dt.total_seconds()==INTERVALS[p['higher']]).all():
        h=frame.iloc[:0].copy()
    features=prepare(frame,h)
    latest=candidate(features.iloc[-1],profile,symbol,mode,risk['fee_pct'],risk['slippage_pct'])
    fresh=0<=(now-frame.iloc[-1].close_time).total_seconds()<seconds
    if not fresh:latest['side']='WAIT';latest['checks']['行情在有效時窗']=False
    latest['observed_at']=str(now)
    db.execute('BEGIN IMMEDIATE')
    try:
        a=account(db,profile,mode,risk,now)
        existing=[json.loads(r[0]) for r in db.execute("SELECT payload FROM strategy_trades WHERE strategy=? AND symbol=? AND mode=? AND status IN ('pending','open','unresolved')",(profile,symbol,mode))]
        for t in existing:
            if t['status']=='unresolved':
                expected=pd.Timestamp(t['last_processed_time'])+pd.Timedelta(seconds=seconds) if t.get('last_processed_time') else pd.Timestamp(t.get('entry_time') or t['eligible_entry_time'])
                if not (frame.time==expected).any():continue
                t.update(status='open' if t.get('entry') is not None else 'pending',reason='已由連續歷史資料還原',recovered_at=str(now))
            if t['status']=='pending':
                eligible=pd.Timestamp(t['eligible_entry_time'])
                future=frame[frame.time>=eligible]
                if future.empty:continue
                if future.iloc[0].time!=eligible:
                    t.update(status='unresolved',reason='預定進場 K 線不在視窗內；資金凍結待歷史還原');save_trade(db,t);continue
                bar=future.iloc[0]
                price=entry_fill(t,bar,t['fee_pct'],t['slippage_pct'])
                if price is None:
                    t.update(status='cancelled',reason='開盤偏離過大或已越過停損／目標',reserved=0.);save_trade(db,t);continue
                actual_unit=abs(price-t['stop'])+(price+t['stop'])*t['fee_pct']/100+t['stop']*t['slippage_pct']/100
                quantity=min(t['quantity'],t['reserved']/(price*(1+t['fee_pct']/100)),t['requested_risk_budget']/actual_unit)
                fee=quantity*price*t['fee_pct']/100
                t.update(status='open',entry=price,quantity=quantity,entry_fee=fee,entry_time=str(bar.time),
                    reserved=quantity*price,bars_held=0,last_processed_time=None,
                    risk_budget=quantity*(abs(price-t['stop'])+(price+t['stop'])*t['fee_pct']/100+t['stop']*t['slippage_pct']/100))
                a['equity']-=fee;equity_event(db,a,now,'進場手續費')
            bars=frame[frame.time>=pd.Timestamp(t['entry_time'])]
            if t.get('last_processed_time'):
                bars=bars[bars.time>pd.Timestamp(t['last_processed_time'])]
            expected=pd.Timestamp(t['last_processed_time'])+pd.Timedelta(seconds=seconds) if t.get('last_processed_time') else pd.Timestamp(t['entry_time'])
            if not bars.empty and bars.iloc[0].time!=expected:
                t.update(status='unresolved',reason='持倉期間行情缺失；不能假定未觸及停損');save_trade(db,t);continue
            for bar in bars.itertuples():
                t['bars_held']+=1;t['last_processed_time']=str(bar.time)
                outcome=exit_on_bar(t,bar)
                if outcome:
                    raw,reason=outcome
                    values=settle_values(t,raw,bar.time if 'gap' in reason else bar.close_time,funding_context)
                    t.update(values,status='closed',exit_reason=reason,settled_at=str(now),reserved=0.)
                    a['equity']+=t['pnl']+t['entry_fee'];equity_event(db,a,now,'出場：'+reason)
                    break
            save_trade(db,t)
        db.execute('INSERT OR REPLACE INTO strategy_latest VALUES (?,?,?,?)',(profile,symbol,mode,dumps(latest)))
        duplicate=db.execute('SELECT 1 FROM strategy_trades WHERE id=?',(latest['id'],)).fetchone()
        active=db.execute("SELECT COUNT(*) FROM strategy_trades WHERE strategy=? AND symbol=? AND mode=? AND status IN ('pending','open','unresolved')",(profile,symbol,mode)).fetchone()[0]
        if allow_new and latest['side']!='WAIT' and not duplicate and not active:
            eligible=eligible_time(latest['signal_time'],now,interval)
            reserved=float(db.execute("SELECT COALESCE(SUM(json_extract(payload,'$.reserved')),0) FROM strategy_trades WHERE strategy=? AND mode=? AND status IN ('pending','open','unresolved')",(profile,mode)).fetchone()[0])
            positions=db.execute("SELECT COUNT(*) FROM strategy_trades WHERE strategy=? AND mode=? AND status IN ('pending','open','unresolved')",(profile,mode)).fetchone()[0]
            frozen=db.execute("SELECT COUNT(*) FROM strategy_trades WHERE strategy=? AND mode=? AND status='unresolved'",(profile,mode)).fetchone()[0]
            reasons=[]
            if frozen:reasons.append('存在無法還原部位，帳戶暫停新進場')
            if positions>=risk['max_positions']:reasons.append('達同策略持倉／預留上限')
            if a['equity']<=a['day_start']*(1-risk['daily_loss_pct']/100):reasons.append('達台北當日已確認損失上限')
            if profile=='intraday' and eligible.tz_convert('Asia/Taipei').date()!=pd.Timestamp(latest['signal_time']).tz_convert('Asia/Taipei').date():reasons.append('禁止當沖跨日進場')
            direction=1 if latest['side']=='LONG' else -1
            price=latest['reference']*(1+direction*risk['slippage_pct']/100)
            unit=abs(price-latest['stop'])+(price+latest['stop'])*risk['fee_pct']/100+latest['stop']*risk['slippage_pct']/100
            available=max(0,a['equity']-reserved)
            budget=min(available,a['equity']*risk['allocation_pct']/100)
            quantity=min(max(0,a['equity'])*risk['risk_pct']/100/unit,budget/(price*(1+risk['fee_pct']/100))) if unit>0 else 0
            if quantity<=0:reasons.append('可用模擬資金不足')
            cost=None;effective_slippage=risk['slippage_pct']
            if mode=='live' and risk.get('quote_costs',False):
                from strategy_risk import snapshot_cost
                cost,error=snapshot_cost(quote_context or {'book_valid':False,'mark':None},latest['side'],risk['slippage_pct'],latest['reference'],latest['atr'],quantity)
                if error:reasons.append(error)
                if cost:
                    effective_slippage=cost['effective_slippage_pct']
                    price=latest['reference']*(1+direction*effective_slippage/100)
                    unit=abs(price-latest['stop'])+(price+latest['stop'])*risk['fee_pct']/100+latest['stop']*effective_slippage/100
                    quantity=min(max(0,a['equity'])*risk['risk_pct']/100/unit,budget/(price*(1+risk['fee_pct']/100)))
            t={**latest,**{k:risk[k] for k in ('fee_pct','slippage_pct','funding_pct_8h')},
                'execution_cost':cost or {'version':'fixed-assumptions-v1','note':'固定成本假設'},'slippage_pct':effective_slippage,
                'created_at':str(now),'eligible_entry_time':str(eligible),'quantity':quantity,
                'reserved':quantity*price*(1+risk['fee_pct']/100) if not reasons else 0.,
                'requested_risk_budget':a['equity']*risk['risk_pct']/100,
                'status':'blocked' if reasons else 'pending','reason':'；'.join(reasons),
                'analysis_context':context or {},'assumptions':('報價快照價差壓測；資金費按覆蓋情況採公開已結算事件或明示估算，非實盤撮合' if cost else '1×紙上資金；費率／滑價固定假設，資金費按固定假設比例估算，非歷史真實結算')}
            from strategy_learning import predictions
            t['model_predictions']=predictions(db,t)
            save_trade(db,t)
        save_account(db,a);db.commit()
    except BaseException:
        db.rollback();raise
    return latest


def summary(db,profile,mode):
    account_row=db.execute('SELECT payload FROM strategy_accounts WHERE strategy=? AND mode=?',(profile,mode)).fetchone()
    a=json.loads(account_row[0]) if account_row else None
    rows=[json.loads(r[0]) for r in db.execute('SELECT payload FROM strategy_trades WHERE strategy=? AND mode=? ORDER BY signal_time',(profile,mode))]
    closed=[r for r in rows if r['status']=='closed']
    gain=sum(max(r['pnl'],0) for r in closed);loss=-sum(min(r['pnl'],0) for r in closed)
    return {'account':a,'rows':rows,'closed':len(closed),'wins':sum(r['pnl']>0 for r in closed),
        'profit_factor':gain/loss if loss else None,'pending':sum(r['status']=='pending' for r in rows),
        'open':sum(r['status']=='open' for r in rows),'unresolved':sum(r['status']=='unresolved' for r in rows),
        'average_r':sum(r.get('net_r',0) or 0 for r in closed)/len(closed) if closed else None}
