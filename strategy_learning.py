"""Strategy-specific supervised shadow learners from PRE-RECORDED forward trades.

Profit and risk evidence replaces win-rate targets. Every prediction is stored before entry. Candidates remain
parallel until enough common future observations support a conservative promotion.
"""
import hashlib
import json
import math
import numpy as np
import pandas as pd
from learning_lab import fit_classifier,predict,trade_stats
from strategy_growth import OBJECTIVE,forward_window,daily_interval,risk_score,compare

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
    rows=forward_window(rows,now)
    n=len(rows);wins=sum(r['pnl']>0 for r in rows)
    bounds=wilson(wins,n)
    stats=trade_stats(rows)
    days=len({pd.Timestamp(r.get('entry_time',r.get('created_at'))).tz_convert('Asia/Taipei').date() for r in rows})
    interval=daily_interval(rows,[r['net_return']*100 for r in rows])
    r_values=[risk_score(r) for r in rows]
    r_interval=daily_interval(rows,r_values) if rows and all(v is not None for v in r_values) else [None,None]
    losses=-sum(min(r['net_return'],0) for r in rows)
    gains=sum(max(r['net_return'],0) for r in rows)
    largest=max([max(r['net_return'],0) for r in rows],default=0)
    checks={'最近7日有模型選擇結算':bool(rows and pd.Timestamp(rows[-1]['exit_time'])>=now-pd.Timedelta(days=7)),
        '無待還原交易':unresolved==0,'真實未來紙上資料':mode=='live','至少20個不同交易日':days>=20,'至少20個不同結算日':len({pd.Timestamp(r['exit_time']).tz_convert('Asia/Taipei').date() for r in rows})>=20,'至少100筆預先記錄交易':n>=100,
        '成本後平均報酬為正':stats['expectancy_pct'] is not None and stats['expectancy_pct']>0,
        '日群聚平均報酬區間下限為正':interval[0] is not None and interval[0]>0,
        '等風險淨R區間下限為正':r_interval[0] is not None and r_interval[0]>0,
        'Profit factor 至少1.1':bool(gains>0 and (losses==0 or gains/losses>=1.1)),
        '單筆正報酬占比不超過25%':gains>0 and largest/gains<=.25,
        '逐筆1×回撤低於15%':stats['max_drawdown_pct']<15}
    return {'objective':OBJECTIVE,'expectancy95_pct':interval,'expectancy95_r':r_interval,'window':'近90天、最近200筆模型選擇的未來結算交易','samples':n,'trading_days':days,'wins':wins,'win_rate':wins/n*100 if n else None,
        'wilson95_pct':[v*100 if v is not None else None for v in bounds],'stats':stats,
        'checks':{k:bool(v) for k,v in checks.items()},'target_pass':all(checks.values()),
        'label':'通過獲利與風險研究門檻，未保證未來獲利' if all(checks.values()) else '獲利與風險證據尚未通過研究門檻'}


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
            scores=[risk_score(r) for r in subset]
            merit=float(sum(scores)/len(validation)) if len(subset)>=20 and all(v is not None for v in scores) and stats['max_drawdown_pct']<15 and stats['expectancy_pct']>0 else -1e9
            if best is None or merit>best[0]:best=(merit,model,threshold,reg,len(subset))
    if best is None or best[0]<=0:return None
    _,model,threshold,reg,count=best
    probabilities=predict(model,[vector(r) for r in testing])
    filtered=[r for r,p in zip(testing,probabilities) if p>=threshold]
    identity=hashlib.sha256(json.dumps(['strategy-logistic-profit-v2',FEATURES,profile,mode,[(r['id'],r['pnl'],r.get('net_r'),r['net_return']) for r in good],threshold,reg,model]).encode()).hexdigest()[:20]
    return {'id':identity,'profile':profile,'mode':mode,'model':model,'threshold':threshold,'features':FEATURES,
        'regularization':reg,'version':'strategy-logistic-profit-v2','objective':OBJECTIVE,'source_ids':[r['id'] for r in good],'trained_at':str(pd.Timestamp.now(tz='UTC')),'source_count':n,
        'split':{'train':len(train),'validation':len(validation),'test':len(testing),
            'train_last_available_at':str(max(available(r) for r in train)),'validation_last_available_at':str(max(available(r) for r in validation)),
            'train_last_outcome':max(r['exit_time'] for r in train),'validation_first_forecast':str(val_start),
            'validation_last_outcome':max(r['exit_time'] for r in validation),'test_first_forecast':str(test_start)},
        'validation_selected':count,'test_selected':len(filtered),'test_stats':trade_stats(filtered),
        'brier':float(np.mean((probabilities-np.asarray([r['pnl']>0 for r in testing]))**2)),
        'shadow_only':True,'note':'驗證集以成本後淨R選參數；模型機率不是已校準勝率，不保證獲利'}


def update(db,profile,mode,now=None):
    from strategy_journal import state
    now=pd.Timestamp(now or pd.Timestamp.now(tz='UTC'))
    current=load(db,profile,mode)
    count=db.execute("SELECT COUNT(*) FROM strategy_trades WHERE strategy=? AND mode=? AND status='closed'",(profile,mode)).fetchone()[0]
    if current.get('objective')==OBJECTIVE and current.get('closed_samples')==count and current.get('unresolved_samples')==db.execute("SELECT COUNT(*) FROM strategy_trades WHERE strategy=? AND mode=? AND status='unresolved'",(profile,mode)).fetchone()[0] and (now-pd.Timestamp(current.get('updated_at','1970-01-01T00:00:00Z'))).total_seconds()<3600:
        return current
    rows=[json.loads(r[0]) for r in db.execute("SELECT payload FROM strategy_trades WHERE strategy=? AND mode=? AND status='closed'",(profile,mode))]
    unresolved=db.execute("SELECT COUNT(*) FROM strategy_trades WHERE strategy=? AND mode=? AND status='unresolved'",(profile,mode)).fetchone()[0]
    incumbent=current.get('incumbent');challenger=current.get('challenger')
    if incumbent:
        chosen=selected_forward(rows,incumbent['id'])
        current['forward_evidence']=evidence(chosen,mode,unresolved,now)
    if challenger:
        comparison=compare(rows,incumbent['id'],challenger['id'],mode,unresolved,now)
        current['competition']=comparison
        new_evidence=evidence(selected_forward(rows,challenger['id']),mode,unresolved,now)
        current['challenger_evidence']=new_evidence
        if comparison['common']>=100 and min(v['selected'] for v in comparison['models'].values())>=100:
            better=new_evidence['target_pass'] and comparison['comparison_pass']
            audit={'at':str(now),'decision':'晉升影子模型' if better else '保留影子模型','old':incumbent['id'],'candidate':challenger['id'],
                'objective':OBJECTIVE,'comparison':comparison,'reason':'共同機會淨R改善且回撤未增加' if better else '未通過：'+'、'.join([k for k,v in {**comparison['checks'],**new_evidence['checks']}.items() if not v])}
            current.setdefault('history',[]).append(audit)
            if better:current['incumbent']=challenger;current['forward_evidence']=new_evidence
            current.pop('challenger',None)
    last=pd.Timestamp(current.get('last_attempt','1970-01-01T00:00:00Z'))
    if not current.get('challenger') and len(rows)>=200 and (now-last).total_seconds()>=86400 and len(rows)-current.get('last_source_count',0)>=20:
        candidate=fit(rows,profile,mode)
        current.update(last_attempt=str(now),last_source_count=len(rows))
        current['last_training']={'at':str(now),'source_count':len(rows),'result':'模型已建立並封存' if candidate else '樣本邊界不足或驗證淨R未為正，未建立新模型'}
        db.execute('INSERT INTO strategy_training_runs(profile,mode,attempted_at,source_count,result,model_id) VALUES (?,?,?,?,?,?)',(profile,mode,str(now),len(rows),current['last_training']['result'],candidate['id'] if candidate else None))
        if candidate:
            db.execute('INSERT OR IGNORE INTO strategy_models VALUES (?,?,?,?,?)',(candidate['id'],profile,mode,candidate['trained_at'],json.dumps(candidate,ensure_ascii=False,allow_nan=False)))
            db.commit()
            if not current.get('incumbent'):current['incumbent']=candidate
            elif candidate['id']!=current['incumbent']['id']:current['challenger']=candidate
    current.update(objective=OBJECTIVE,closed_samples=len(rows),unresolved_samples=unresolved,updated_at=str(now))
    state(db,f'learner/{profile}/{mode}',current)
    return current
