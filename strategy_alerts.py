"""Explicit opt-in alerts only after pre-recorded live learner evidence qualifies."""
import json
import time
import pandas as pd
from strategy_learning import load,evidence,selected_forward
from strategy_journal import dumps
from strategy_rules import PROFILES


def emit(db,signals,plan,settings,now=None):
    now=time.time() if now is None else now
    if not (settings.get('strategy_notifications') and settings['notifications_enabled'] and settings['channel']=='telegram' and plan['mode']=='live'):
        return None
    if db.execute("SELECT COUNT(*) FROM strategy_trades WHERE strategy=? AND mode='live' AND status='unresolved'",(plan['strategy'],)).fetchone()[0]:return None
    model=load(db,plan['strategy'],'live');incumbent=model.get('incumbent')
    if not incumbent:return None
    closed=[json.loads(r[0]) for r in db.execute("SELECT payload FROM strategy_trades WHERE strategy=? AND mode='live' AND status='closed'",(plan['strategy'],))]
    proof=evidence(selected_forward(closed,incumbent['id']),'live',now=pd.Timestamp(now,unit='s',tz='UTC'))
    if not proof['target_pass']:return None
    row=db.execute('SELECT payload FROM strategy_trades WHERE id=?',(plan['id'],)).fetchone()
    if not row:return None
    trade=json.loads(row[0])
    if trade['status']!='pending' or not any(p['model_id']==incumbent['id'] and p['selected'] for p in trade.get('model_predictions',[])):return None
    expiration=pd.Timestamp(trade['eligible_entry_time']).timestamp()
    if expiration<=now:return None
    quote=signals.execute("SELECT payload FROM scan_results WHERE symbol=? AND mode='live' ORDER BY updated_at DESC LIMIT 1",(plan['symbol'],)).fetchone()
    quote=json.loads(quote[0]) if quote else {}
    mark=quote.get('mark_price');stamp=quote.get('mark_time')
    if mark is None or stamp is None or not 0<=now-stamp<=180 or abs(mark-plan['reference'])>.75*plan['atr']:return None
    identity='strategy-'+plan['id']
    payload={**trade,'kind':'strategy_signal','entry':plan['reference'],'targets':[plan['target']],
        'mark_price':mark,'candle_time':plan['signal_time'],'expires_at':expiration,
        'model_id':incumbent['id'],'model_probability':None,'score':0,
        'factors':[{'name':key,'score':0,'evidence':'通過' if value else '未通過'} for key,value in plan['checks'].items()],
        'strategy_context':{'profile':PROFILES[plan['strategy']]['name'],'version':plan['profile_version']},
        'forward_evidence':proof,'news':[]}
    with signals:
        result=signals.execute('INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?,?,?)',(identity,now,expiration,plan['symbol'],plan['interval'],plan['side'],'live',dumps(payload)))
    return identity if result.rowcount else None
