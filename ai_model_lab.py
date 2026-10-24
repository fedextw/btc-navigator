"""Bounded, immutable multi-family shadow research with chronological calibration."""
import hashlib
import json
import math
import numpy as np
import pandas as pd
from learning_lab import fit_classifier,predict,trade_stats
from strategy_growth import risk_score,compare
from ai_context_features import extract,NAMES,VERSION

FAMILIES=['technical-logistic','technical-naive-bayes','regime-logistic','news-logistic','funding-logistic','context-logistic']
CONTEXT_FIELDS={'news-logistic':NAMES[:4],'funding-logistic':NAMES[4:],'context-logistic':NAMES}
COMPARISONS=9


def features(plan,family):
    from strategy_learning import vector
    x=vector(plan)
    if family in CONTEXT_FIELDS:x += [extract(plan)['values'][name] for name in CONTEXT_FIELDS[family]]
    return x


def raw_score(model,plan):
    x=features(plan,model['family']);engine=model['engine'];regime=plan.get('context',{}).get('regime')
    if model['family']=='regime-logistic':
        engine=engine.get(regime)
        if engine is None:return None
    if model['family']=='technical-naive-bayes':
        z=(np.asarray(x)-np.asarray(model['support']['mean']))/np.asarray(model['support']['scale'])
        scores=[math.log(engine['prior'][k])-.5*np.sum(np.log(2*np.pi*np.asarray(engine['var'][k]))+(z-np.asarray(engine['mean'][k]))**2/np.asarray(engine['var'][k])) for k in range(2)]
        return float(1/(1+np.exp(np.clip(scores[0]-scores[1],-35,35))))
    return float(predict(engine,[x])[0])


def forecast(model,plan):
    raw=raw_score(model,plan);uncertain=[]
    x=np.asarray(features(plan,model['family']));support=model['support']
    z=np.abs((x-np.asarray(support['mean']))/np.asarray(support['scale']))
    if int((z>6).sum())>=2:uncertain.append('至少兩項特徵超出訓練分布6個尺度')
    if plan.get('context',{}).get('regime') not in support['regimes']:uncertain.append('訓練未涵蓋此行情')
    if raw is None:uncertain.append('此行情沒有足夠樣本的專屬模型')
    if model['family'] in CONTEXT_FIELDS and not any(extract(plan)['values'][k] for k in CONTEXT_FIELDS[model['family']] if k.endswith('available')):uncertain.append('沒有事前可用的新聞或市場背景')
    calibration=model.get('calibrator');probability=raw
    if raw is not None and calibration:
        logit=math.log(max(1e-6,raw)/max(1e-6,1-raw));probability=float(predict(calibration,[[logit]])[0])
    return {'model_id':model['id'],'family':model['family'],'raw_probability':raw,'probability':probability,
            'calibrated':bool(calibration),'abstained':bool(uncertain),'uncertainty':uncertain,
            'selected':bool(probability is not None and probability>=model['threshold'] and not uncertain),
            'threshold':model['threshold'],'feature_version':VERSION if model['family'] in CONTEXT_FIELDS else 'technical-v1'}


def fit_family(rows,profile,mode,family,now=None):
    now=pd.Timestamp(now if now is not None else pd.Timestamp.now(tz='UTC'))
    good=[]
    for r in rows:
        try:
            available=max(pd.Timestamp(r['exit_time']),pd.Timestamp(r.get('settled_at',r['exit_time'])))
            if r['status']!='closed' or r.get('mode')!=mode or r.get('strategy')!=profile or r.get('source')=='historical_replay' or available>now or risk_score(r) is None:continue
            x=features(r,family)
            if np.isfinite(x).all():good.append(r)
        except (KeyError,ValueError,TypeError):continue
    good=sorted(good,key=lambda r:(pd.Timestamp(r['created_at']),r['id']))[-2000:]
    if len(good)<300:return None
    a,b=int(len(good)*.6),int(len(good)*.8);mid=a+(b-a)//2
    known=lambda r:max(pd.Timestamp(r['exit_time']),pd.Timestamp(r.get('settled_at',r['exit_time'])))
    train=[r for r in good[:a] if known(r)<pd.Timestamp(good[a]['created_at'])]
    calibrate=[r for r in good[a:mid] if known(r)<pd.Timestamp(good[mid]['created_at'])]
    validation=[r for r in good[mid:b] if known(r)<pd.Timestamp(good[b]['created_at'])]
    testing=good[b:]
    if min(len(train),len(calibrate),len(validation),len(testing))<20 or len(train)<80:return None
    x=np.asarray([features(r,family) for r in train]);y=np.asarray([r['pnl']>0 for r in train],float)
    if min(int(y.sum()),int((1-y).sum()))<5:return None
    if family in CONTEXT_FIELDS and sum(any(extract(r)['values'][k] for k in CONTEXT_FIELDS[family] if k.endswith('available')) for r in train)<60:return None
    mean=x.mean(axis=0);scale=x.std(axis=0);scale=np.where(scale<1e-6,1e-6,scale)
    support={'mean':mean.tolist(),'scale':scale.tolist(),'regimes':sorted({r['context']['regime'] for r in train})}
    if family=='technical-naive-bayes':
        z=(x-mean)/scale
        engine={'mean':[z[y==k].mean(axis=0).tolist() for k in (0,1)],'var':[(z[y==k].var(axis=0)+.1).tolist() for k in (0,1)],'prior':[float((y==k).mean()) for k in (0,1)]}
    elif family=='regime-logistic':
        engine={}
        for regime in support['regimes']:
            indices=[i for i,r in enumerate(train) if r['context']['regime']==regime]
            labels=y[indices]
            if len(indices)>=60 and min(int(labels.sum()),int((1-labels).sum()))>=5:engine[regime]=fit_classifier(x[indices],labels,.01)
        if not engine:return None
    else:engine=fit_classifier(x,y,.01)
    model={'id':'training','family':family,'engine':engine,'support':support,'calibrator':None,'threshold':.5}
    calibration=[(raw_score(model,r),r['pnl']>0) for r in calibrate]
    calibration=[(p,y) for p,y in calibration if p is not None]
    if len(calibration)>=20 and min(sum(y for p,y in calibration),sum(not y for p,y in calibration))>=3:
        logits=np.asarray([[math.log(max(1e-6,p)/max(1e-6,1-p))] for p,y in calibration]);labels=np.asarray([y for p,y in calibration],float)
        model['calibrator']=fit_classifier(logits,labels,.01)
    forecasts=[forecast(model,r) for r in validation]
    best=None
    for threshold in (0.,.05,.1,.2,.3,.4,.5,.6,.7,.8):
        subset=[r for r,p in zip(validation,forecasts) if p['probability'] is not None and p['probability']>=threshold and not p['abstained']]
        stats=trade_stats(subset)
        if len(subset)<20 or stats['max_drawdown_pct']>=15 or stats['expectancy_pct']<=0:continue
        merit=sum(risk_score(r) for r in subset)/len(validation)
        if merit>0 and (best is None or merit>best[0]):best=(merit,threshold,len(subset))
    if best is None:return None
    model['threshold']=best[1]
    test_predictions=[forecast(model,r) for r in testing]
    chosen=[r for r,p in zip(testing,test_predictions) if p['selected']]
    identifier=hashlib.sha256(json.dumps(['multi-family-v1',VERSION,family,profile,mode,model,[(r['id'],r['pnl'],r['net_r'],extract(r)['values']) for r in good]],sort_keys=True).encode()).hexdigest()[:20]
    from strategy_learning import FEATURES
    model.update(id=identifier,profile=profile,mode=mode,features=list(FEATURES)+CONTEXT_FIELDS.get(family,[]),
                 version='multi-family-v1',trained_at=str(now),source_ids=[r['id'] for r in good],source_count=len(good),base_rate=float(y.mean()),
                 test_stats=trade_stats(chosen),test_selected=len(chosen),validation_selected=best[2],shadow_only=True,
                 split={'train':len(train),'calibration':len(calibrate),'validation':len(validation),'test':len(testing),
                        'train_last_available':str(max(known(r) for r in train)),'calibration_first':calibrate[0]['created_at'],
                        'calibration_last_available':str(max(known(r) for r in calibrate)),'validation_first':validation[0]['created_at'],
                        'validation_last_available':str(max(known(r) for r in validation)),'test_first':testing[0]['created_at']},
                 note='獨立校準段→驗證選門檻→保留測試；多模型仍需共同未來競賽，不以回測升級')
    return model


def load_lab(db,profile,mode):
    row=db.execute('SELECT payload FROM strategy_state WHERE name=?',(f'ai-lab/{profile}/{mode}',)).fetchone()
    return json.loads(row[0]) if row else {}


def update_lab(db,profile,mode,now=None):
    from strategy_learning import load,evidence,selected_forward
    from strategy_journal import state
    from ai_diagnostics import health,reliability
    now=pd.Timestamp(now if now is not None else pd.Timestamp.now(tz='UTC'))
    current=load(db,profile,mode);lab=load_lab(db,profile,mode)
    rows=[json.loads(r[0]) for r in db.execute("SELECT payload FROM strategy_trades WHERE strategy=? AND mode=? AND status='closed'",(profile,mode))]
    unresolved=db.execute("SELECT COUNT(*) FROM strategy_trades WHERE strategy=? AND mode=? AND status='unresolved'",(profile,mode)).fetchone()[0]
    incumbent=current.get('incumbent')
    # Refresh diagnostics on new settlements or at least hourly; no fake checks every frame.
    if lab.get('version')=='ai-lab-v1' and lab.get('incumbent_id')==(incumbent or {}).get('id') and lab.get('closed_count')==len(rows) and lab.get('unresolved')==unresolved and (now-pd.Timestamp(lab['updated_at'])).total_seconds()<3600:return lab
    models=[m for m in [incumbent,current.get('challenger'),*lab.get('contenders',[])] if m]
    lab['diagnostics']={m['id']:{'health':health(rows,m['id'],now),'reliability':reliability(rows,m['id'],now)} for m in models}
    contenders=lab.get('contenders',[]);round_reports=[];completed_round=False
    if incumbent and contenders:
        for model in contenders:
            report=compare(rows,incumbent['id'],model['id'],mode,unresolved,now,alpha=.05/COMPARISONS)
            proof=evidence(selected_forward(rows,model['id']),mode,unresolved,now)
            report.update(candidate_id=model['id'],family=model['family'],qualified=bool(proof['target_pass'] and not health(rows,model['id'],now)['pause_qualified']))
            round_reports.append(report)
        ready=all(r['common']>=100 and min(m['selected'] for m in r['models'].values())>=100 for r in round_reports)
        if ready:
            completed_round=True
            passed=[r for r in round_reports if r['comparison_pass'] and r['qualified']]
            winner=max(passed,key=lambda r:r['delta_mean_r']) if passed else None
            audit={'at':str(now),'decision':'晉升多模型候選' if winner else '保留現行模型','reports':round_reports,'reason':'共同未來機會、成本後淨R／回撤與多重比較修正'}
            if winner:
                chosen=next(m for m in contenders if m['id']==winner['candidate_id'])
                current['incumbent']=chosen
                current.setdefault('history',[]).append({'at':str(now),'decision':'晉升影子模型','old':incumbent['id'],'candidate':chosen['id'],'reason':audit['reason'],'comparison':winner})
                # Old pairwise challenger must restart against the new incumbent.
                current.pop('challenger',None);current['forward_evidence']=evidence(selected_forward(rows,chosen['id']),mode,unresolved,now)
                state(db,f'learner/{profile}/{mode}',current)
            lab.setdefault('round_history',[]).append(audit);lab['contenders']=[]
        elif (now-pd.Timestamp(lab.get('round_started',str(now)))).days>=90:
            completed_round=True
            lab.setdefault('round_history',[]).append({'at':str(now),'decision':'樣本不足結束觀察','reports':round_reports});lab['contenders']=[]
    lab['competitions']=round_reports
    baseline=next((m for m in contenders if m['family']=='technical-logistic'),None)
    if baseline:
        lab['ablations']=[{**compare(rows,baseline['id'],m['id'],mode,unresolved,now,alpha=.05/COMPARISONS),'family':m['family']} for m in contenders if m['family'] in CONTEXT_FIELDS]
    elif not contenders:lab['ablations']=[]
    if completed_round:lab['round_history'][-1]['ablations']=lab.get('ablations',[])
    last=pd.Timestamp(lab.get('last_training','1970-01-01T00:00:00Z'))
    if incumbent and not lab.get('contenders') and len(rows)>=300 and len(rows)-lab.get('training_count',0)>=40 and (now-last).total_seconds()>=3*86400:
        lab['competitions']=[];lab['ablations']=[]
        trained=[];attempts=[]
        for family in FAMILIES:
            model=fit_family(rows,profile,mode,family,now)
            attempts.append({'at':str(now),'family':family,'source_count':len(rows),'result':'封存、等待未來競賽' if model else '資料／校準邊界／背景覆蓋或驗證獲利不足'})
            if model and model['id']!=incumbent['id']:
                db.execute('INSERT OR IGNORE INTO strategy_models VALUES (?,?,?,?,?)',(model['id'],profile,mode,model['trained_at'],json.dumps(model,ensure_ascii=False,allow_nan=False)));trained.append(model)
        db.commit();lab.update(contenders=trained,last_training=str(now),training_count=len(rows),round_started=str(now))
        lab.setdefault('attempts',[]).extend(attempts)
    lab.update(incumbent_id=(current.get('incumbent') or {}).get('id'),version='ai-lab-v1',updated_at=str(now),closed_count=len(rows),unresolved=unresolved)
    state(db,f'ai-lab/{profile}/{mode}',lab)
    return lab
