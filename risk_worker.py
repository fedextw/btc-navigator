"""Independent public quote heartbeat, sharing exchange request budget."""
import time
from signal_store import connect,set_state,get_state
from strategy_risk import quote


def collect(client,root):
    db=connect(root)
    try:
        marks=client.json('/fapi/v1/premiumIndex',weight=10)
        if not isinstance(marks,list):raise ValueError('標記價格格式異常')
        # Save fresh marks even if book collection fails; never keep an old book marked fresh.
        state={'mode':'live','updated_at':time.time(),'marks':{r['symbol']:r for r in marks if isinstance(r,dict) and 'symbol' in r},'books':{},'error':None}
        try:
            books=client.json('/fapi/v1/ticker/bookTicker',weight=5)
            if not isinstance(books,list):raise ValueError('買賣報價格式異常')
            state['books']={r['symbol']:r for r in books if isinstance(r,dict) and 'symbol' in r}
        except Exception as exc:state['error']=type(exc).__name__
        set_state(db,'risk_quotes',state)
        return state
    finally:db.close()


def quotes(root,now=None,mode='live'):
    db=connect(root)
    try:raw=get_state(db,'risk_quotes',{})
    finally:db.close()
    # Assess each exchange timestamp at read time, not only the worker heartbeat.
    if raw.get('mode','live')!=mode:return {},raw
    return {s:quote(m,raw.get('books',{}).get(s,{}),now) for s,m in raw.get('marks',{}).items()},raw


def loop(root,client,stopped):
    while not stopped.is_set():
        try:collect(client,root)
        except Exception as exc:
            db=connect(root)
            try:
                old=get_state(db,'risk_quotes',{});old.update(error=type(exc).__name__,last_attempt=time.time());set_state(db,'risk_quotes',old)
            finally:db.close()
        stopped.wait(30)
