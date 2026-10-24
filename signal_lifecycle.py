"""Append-only observed lifecycle. Reference validity is separate from paper execution."""
import hashlib
import json
import time
import pandas as pd

KINDS={'created':'候選成立','baseline':'舊紀錄快照','open':'模擬成交','closed':'模擬出場','cancelled':'模擬取消',
       'blocked':'候選阻擋','unresolved':'路徑未知','recovered':'路徑恢復','reference_paused':'參考暫停','reference_valid':'參考有效','reference_expired':'參考過期'}
NOTIFY=('open','closed','cancelled','unresolved','recovered','reference_paused','reference_valid','reference_expired')


def append(db,t,kind,observed_at,detail=None,effective_at=None):
    db.execute('INSERT INTO strategy_lifecycle(trade_id,kind,observed_at,effective_at,payload) VALUES (?,?,?,?,?)',
        (t['id'],kind,str(pd.Timestamp(observed_at).tz_convert('UTC')),str(pd.Timestamp(effective_at).tz_convert('UTC')) if effective_at else None,json.dumps(detail or {},ensure_ascii=False,allow_nan=False)))


def track_save(db,old,t,observed_at,new_forecast=False):
    has=db.execute('SELECT 1 FROM strategy_lifecycle WHERE trade_id=? LIMIT 1',(t['id'],)).fetchone()
    if not has:
        append(db,t,'created' if new_forecast else 'baseline',observed_at,{'status':old['status'] if old else t['status'],'note':'當時觀測' if new_forecast else '升級後首次快照，不代表歷史事件發生時間'})
    if old and old['status']!=t['status']:
        kind='recovered' if old['status']=='unresolved' and t['status'] in ('pending','open') else t['status']
        append(db,t,kind,observed_at,{'from':old['status'],'to':t['status'],'reason':t.get('exit_reason') or t.get('reason','')},t.get('exit_time') if kind=='closed' else t.get('entry_time') if kind=='open' else None)
    elif not old and new_forecast and t['status']=='blocked':append(db,t,'blocked',observed_at,{'reason':t.get('reason')})


def reference_status(t,q,now,safety=None,unknown=False):
    if t['status']!='pending':return 'not_pending','已非待進場候選'
    if now>=pd.Timestamp(t['eligible_entry_time']):return 'expired','參考期限已到，等待K線確認紙上成交；不是新的入場點'
    if unknown:return 'paused','策略有無法還原部位'
    if safety and safety['blocked']:return 'paused','AI風險／行情觀察中'
    stamp=q.get('mark_time');mark=q.get('mark')
    if mark is None or stamp is None or not 0<=now.timestamp()-stamp<=120:return 'paused','標記價格缺漏或超過120秒'
    if abs(mark-t['reference'])>.75*t['atr']:return 'paused','價格偏離參考進場超過0.75ATR'
    return 'valid','報價與參考期限有效，仍是紙上研究候選'


def refresh(root,now=None):
    from strategy_journal import connect
    from signal_store import connect as signals_db
    from risk_worker import quotes
    from strategy_learning import load
    from ai_diagnostics import guard
    now=pd.Timestamp(now if now is not None else pd.Timestamp.now(tz='UTC')).tz_convert('UTC')
    db=connect(root);signals=signals_db(root)
    try:
        q,_=quotes(root,now.timestamp());profiles={}
        pending=[json.loads(r[0]) for r in db.execute("SELECT payload FROM strategy_trades WHERE mode='live' AND status='pending'")]
        for t in pending:
            if t['strategy'] not in profiles:
                rows=[json.loads(r[0]) for r in db.execute("SELECT payload FROM strategy_trades WHERE strategy=? AND mode='live' AND status='closed'",(t['strategy'],))]
                model=load(db,t['strategy'],'live').get('incumbent')
                unknown=db.execute("SELECT COUNT(*) FROM strategy_trades WHERE strategy=? AND mode='live' AND status='unresolved'",(t['strategy'],)).fetchone()[0]
                profiles[t['strategy']]=(rows,model,unknown)
            rows,model,unknown=profiles[t['strategy']]
            safety=guard(rows,model['id'],t,now) if model else None
            value,reason=reference_status(t,q.get(t['symbol'],{}),now,safety,unknown)
            with db:
                old=db.execute('SELECT status FROM strategy_reference WHERE trade_id=?',(t['id'],)).fetchone()
                if not old or old[0]!=value:
                    append(db,t,'reference_'+value,now,{'reason':reason},t['eligible_entry_time'] if value=='expired' else None)
                db.execute('INSERT OR REPLACE INTO strategy_reference VALUES (?,?,?,?)',(t['id'],value,reason,str(now)))
        enqueue_updates(db,signals,root,now)
        return {'pending_checked':len(pending),'updated_at':str(now)}
    finally:db.close();signals.close()


def enqueue_updates(db,signals,root,now):
    from monitor_settings import load_settings
    s=load_settings(root)
    if not (s['notifications_enabled'] and s['channel']=='telegram' and s.get('strategy_lifecycle_notifications',True)):return
    # Only trades with a recent meaningful change; raw never-published candidates never notify.
    cutoff=str(now-pd.Timedelta(minutes=30))
    ids=[r[0] for r in db.execute("SELECT DISTINCT trade_id FROM strategy_lifecycle WHERE observed_at>=? AND kind NOT IN ('created','baseline','blocked')",(cutoff,))]
    for identity in ids:
        base=signals.execute("SELECT e.id FROM events e JOIN deliveries d ON d.event_id=e.id AND d.channel='telegram' WHERE e.id=? AND d.status='sent'",('strategy-'+identity,)).fetchone()
        if not base:continue
        record=db.execute('SELECT payload FROM strategy_trades WHERE id=?',(identity,)).fetchone()
        if not record:continue
        t=json.loads(record[0])
        if t['mode']!='live':continue
        event=db.execute("SELECT * FROM strategy_lifecycle WHERE trade_id=? AND kind NOT IN ('created','baseline','blocked') ORDER BY id DESC LIMIT 1",(identity,)).fetchone()
        if not event or pd.Timestamp(event['observed_at'])<now-pd.Timedelta(minutes=30):continue
        # Initial valid check is not an update to an already sent signal; notify recovery only.
        if event['kind']=='reference_valid':
            paused=db.execute("SELECT id FROM strategy_lifecycle WHERE trade_id=? AND kind='reference_paused' AND id<? ORDER BY id DESC LIMIT 1",(identity,event['id'])).fetchone()
            if not paused:continue
            delivered_pause=signals.execute("SELECT 1 FROM deliveries WHERE event_id=? AND channel='telegram' AND status='sent'",('lifecycle-'+str(paused[0])+'-'+identity,)).fetchone()
            if not delivered_pause:continue
        if event['kind']=='reference_expired' and event['effective_at'] and pd.Timestamp(event['effective_at'])<now-pd.Timedelta(minutes=30):continue
        key='lifecycle-'+str(event['id'])+'-'+identity
        payload={'kind':'strategy_lifecycle','trade_id':identity,'lifecycle_id':event['id'],'base_event_id':base[0],
                 'symbol':t['symbol'],'interval':t['interval'],'strategy':t['strategy'],'side':t['side'],'state':event['kind'],
                 'observed_at':event['observed_at'],'effective_at':event['effective_at'],'details':json.loads(event['payload']),
                 'status':t['status'],'pnl':t.get('pnl'),'mode':'live','expires_at':now.timestamp()+1800}
        with signals:
            signals.execute('INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?,?,?)',(key,now.timestamp(),now.timestamp()+1800,t['symbol'],t['interval'],t['side'],'live',json.dumps(payload,ensure_ascii=False,allow_nan=False)))


def delivery_allowed(root,signals,payload):
    from monitor_settings import load_settings
    from strategy_journal import connect
    if not load_settings(root).get('strategy_lifecycle_notifications',True):return False
    base=signals.execute("SELECT 1 FROM deliveries WHERE event_id=? AND channel='telegram' AND status='sent'",(payload['base_event_id'],)).fetchone()
    if not base:return False
    db=connect(root)
    try:
        row=db.execute("SELECT id FROM strategy_lifecycle WHERE trade_id=? AND kind NOT IN ('created','baseline','blocked') ORDER BY id DESC LIMIT 1",(payload['trade_id'],)).fetchone()
        return bool(row and row[0]==payload['lifecycle_id'])
    finally:db.close()
