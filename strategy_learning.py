"""Strategy-specific supervised shadow learners from PRE-RECORDED forward trades.

No promise of 75%. Every prediction is stored before entry. Candidates remain
parallel until enough common future observations support a conservative promotion.
"""
import hashlib
import json
import math
import numpy as np
import pandas as pd
from learning_lab import fit_classifier,predict,trade_stats

FEATURES=['rsi','macd_ratio','atr_ratio','volume','vwap_gap','higher_adx','direction','session_sin','session_cos','regime_up','regime_down','regime_range']


def vector(plan):
    c=plan['context'];i=c['indicators'];price=i['close']
    values=[i['rsi']/100,i['macd_hist']/price,i['atr']/price,i['volume_ratio'],(price-i['vwap'])/price,
        i['higher_adx']/100,1 if plan.get('side')=='LONG' else -1,
        math.sin(2*math.pi*{'台北00–08':0,'台北08–16':8,'台北16–24':16}[c['session']]/24),
        math.cos(2*math.pi*{'台北00–08':0,'台北08–16':8,'台北16–24':16}[c['session']]/24),
        float(c['regime']=='trend_up'),float(c['regime']=='trend_down'),float(c['regime']=='range')]

    if not np.isfinite(values).all():raise ValueError('策略特徵不足')
    return values


def wilson(wins,n):
    if not n:return [None,None]
    z=1.95996398454;p=wins/n;d=1+z*z/n
    center=(p+z*z/(2*n))/d;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [max(0,center-half),min(1,center+half)]


def evidence(rows,mode,unresolved=0,now=None):
    now=pd.Timestamp(now or pd.Timestamp.now(tz='UTC'))
    rows=sorted([r for r in rows if r.get('status')=='closed' and now-pd.Timedelta(days=90)<=pd.Timestamp(r['exit_time'])<=now],key=lambda r:(pd.Timestamp(r['exit_time']),r['id']))[-200:]
    n=len(rows);wins=sum(r['pnl']>0 for r in rows)
    bounds=wilson(wins,n)
    stats=trade_stats(rows)
    days=len({pd.Timestamp(r.get('entry_time',r.get('created_at'))).tz_convert('Asia/Taipei').date() for r in rows})
    checks={'最近7日有模型選擇結算':bool(rows and pd.Timestamp(rows[-1]['exit_time'])>=now-pd.Timedelta(days=7)),'無待還原交易':unresolved==0,'真實未來紙上資料':mode=='live','至少20個不同交易日':days>=20,'至少100筆預先記錄交易':n>=100,
        '觀察勝率至少75%':n>0 and wins/n>=.75,
        '95%區間下限至少75%':bounds[0] is not None and bounds[0]>=.75,
        '成本後平均報酬為正':stats['expectancy_pct'] is not None and stats['expectancy_pct']>0,
        'Profit factor 至少1.1':stats['profit_factor'] is not None and stats['profit_factor']>=1.1,
        '逐筆1×回撤低於15%':stats['max_drawdown_pct']<15}
    return {'window':'近90天、最近200筆模型選擇的未來結算交易','samples':n,'trading_days':days,'wins':wins,'win_rate':wins/n*100 if n else None,
        'wilson95_pct':[v*100 if v is not None else None for v in bounds],'stats':stats,
        'checks':{k:bool(v) for k,v in checks.items()},'target_pass':all(checks.values()),
        'label':'達歷史研究門檻，未保證未來勝率' if all(checks.values()) else '75%目標尚未通過研究門檻'}


def load(db,profile,mode):
    row=db.execute('SELECT payload FROM strategy_state WHERE name=?',(f'learner/{profile}/{mode}',)).fetchone()
    return json.loads(row[0]) if row else {}


def predictions(db,plan):
    current=load(db,plan['strategy'],plan['mode']);out=[]
    try:x=vector(plan)
    except (ValueError,KeyError,TypeError):return out
    for role in ('incumbent','challenger'):
        model=current.get(role)
        if model:
            probability=float(predict(model['model'],[x])[0])
            out.append({'role':role,'model_id':model['id'],'probability':probability,
                        'selected':probability>=model['threshold'],'threshold':model['threshold']})
    return out


def selected_forward(rows,model_id):
    return [r for r in rows if any(p['model_id']==model_id and p['selected'] for p in r.get('model_predictions',[]))]


def fit(rows,profile,mode):
    good=[]
    for r in sorted(rows,key=lambda r:(pd.Timestamp(r['created_at']),r['id'])):
        try:vector(r);good.append(r)
        except (KeyError,ValueError,TypeError):continue
    good=good[-2000:]
    if len(good)<200:return None
    n=len(good);v=int(n*.6);t=int(n*.8)
    val_start=pd.Timestamp(good[v]['created_at']);test_start=pd.Timestamp(good[t]['created_at'])
    available=lambda r:max(pd.Timestamp(r['exit_time']),pd.Timestamp(r.get('settled_at',r['exit_time'])))
    train=[r for r in good[:v] if available(r)<val_start]
    validation=[r for r in good[v:t] if available(r)<test_start]
    testing=good[t:]
    if len(train)<80 or len(validation)<20 or len(testing)<30:return None
    x=np.asarray([vector(r) for r in train]);y=np.asarray([r['pnl']>0 for r in train],float)
    best=None
    for reg in (.001,.01,.1):
        model=fit_classifier(x,y,reg)
        p=predict(model,[vector(r) for r in validation])
        for threshold in (.55,.60,.65,.70,.75,.80):
            subset=[r for r,q in zip(validation,p) if q>=threshold]
            stats=trade_stats(subset)
            merit=stats['expectancy_pct'] if len(subset)>=20 else -1e9
            if best is None or merit>best[0]:best=(merit,model,threshold,reg,len(subset))
    _,model,threshold,reg,count=best
    probabilities=predict(model,[vector(r) for r in testing])
    filtered=[r for r,p in zip(testing,probabilities) if p>=threshold]
    identity=hashlib.sha256(json.dumps(['strategy-logistic-v1',FEATURES,profile,mode,[(r['id'],r['pnl']) for r in good],threshold,reg,model]).encode()).hexdigest()[:20]
    return {'id':identity,'profile':profile,'mode':mode,'model':model,'threshold':threshold,'features':FEATURES,
        'regularization':reg,'version':'strategy-logistic-v1','source_ids':[r['id'] for r in good],'trained_at':str(pd.Timestamp.now(tz='UTC')),'source_count':n,
        'split':{'train':len(train),'validation':len(validation),'test':len(testing),
            'train_last_available_at':str(max(available(r) for r in train)),'validation_last_available_at':str(max(available(r) for r in validation)),
            'train_last_outcome':max(r['exit_time'] for r in train),'validation_first_forecast':str(val_start),
            'validation_last_outcome':max(r['exit_time'] for r in validation),'test_first_forecast':str(test_start)},
        'validation_selected':count,'test_selected':len(filtered),'test_stats':trade_stats(filtered),
        'brier':float(np.mean((probabilities-np.asarray([r['pnl']>0 for r in testing]))**2)),
        'shadow_only':True,'note':'模型輸出不是已校準勝率；不依訓練集勝率標示75%達標'}


def update(db,profile,mode,now=None):
    from strategy_journal import state
    now=pd.Timestamp(now or pd.Timestamp.now(tz='UTC'))
    current=load(db,profile,mode)
    count=db.execute("SELECT COUNT(*) FROM strategy_trades WHERE strategy=? AND mode=? AND status='closed'",(profile,mode)).fetchone()[0]
    if current.get('closed_samples')==count and (count<200 or current.get('challenger') or count-current.get('last_source_count',0)<20):
        return current
    rows=[json.loads(r[0]) for r in db.execute("SELECT payload FROM strategy_trades WHERE strategy=? AND mode=? AND status='closed'",(profile,mode))]
    unresolved=db.execute("SELECT COUNT(*) FROM strategy_trades WHERE strategy=? AND mode=? AND status='unresolved'",(profile,mode)).fetchone()[0]
    incumbent=current.get('incumbent');challenger=current.get('challenger')
    if incumbent:
        chosen=selected_forward(rows,incumbent['id'])
        current['forward_evidence']=evidence(chosen,mode,unresolved,now)
    if challenger:
        paired=sorted([r for r in rows if now-pd.Timedelta(days=90)<=pd.Timestamp(r['exit_time'])<=now and {incumbent['id'],challenger['id']}.issubset({p['model_id'] for p in r.get('model_predictions',[])})],key=lambda r:(pd.Timestamp(r['exit_time']),r['id']))[-200:]
        old=selected_forward(paired,incumbent['id']);new=selected_forward(paired,challenger['id'])
        new_evidence=evidence(new,mode,unresolved,now);old_evidence=evidence(old,mode,unresolved,now);old_stats=old_evidence['stats']
        current['challenger_evidence']=new_evidence
        if min(old_evidence['samples'],new_evidence['samples'])>=100:
            better=new_evidence['target_pass'] and new_evidence['stats']['expectancy_pct']>old_stats['expectancy_pct'] and new_evidence['stats']['max_drawdown_pct']<=old_stats['max_drawdown_pct']
            audit={'at':str(now),'decision':'晉升影子模型' if better else '保留影子模型','old':incumbent['id'],'candidate':challenger['id'],
                'old_samples':len(old),'new_samples':len(new),'reason':'共同未來樣本、75%區間與成本後表現比較'}
            current.setdefault('history',[]).append(audit)
            if better:current['incumbent']=challenger;current['forward_evidence']=new_evidence
            current.pop('challenger',None)
    last=pd.Timestamp(current.get('last_attempt','1970-01-01T00:00:00Z'))
    if not current.get('challenger') and len(rows)>=200 and (now-last).total_seconds()>=86400 and len(rows)-current.get('last_source_count',0)>=20:
        candidate=fit(rows,profile,mode)
        current.update(last_attempt=str(now),last_source_count=len(rows))
        if candidate:
            db.execute('INSERT OR IGNORE INTO strategy_models VALUES (?,?,?,?,?)',(candidate['id'],profile,mode,candidate['trained_at'],json.dumps(candidate,ensure_ascii=False,allow_nan=False)))
            db.commit()
            if not current.get('incumbent'):current['incumbent']=candidate
            elif candidate['id']!=current['incumbent']['id']:current['challenger']=candidate
    current.update(closed_samples=len(rows),updated_at=str(now))
    state(db,f'learner/{profile}/{mode}',current)
    return current
