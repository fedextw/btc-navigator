"""Forward-only regime, degradation and reliability evidence; no win-rate promises."""
import math
import numpy as np
import pandas as pd
from strategy_growth import forward_window,daily_interval,risk_score,r_drawdown


def prediction(row,model_id):
    return next((p for p in row.get('model_predictions',[]) if p['model_id']==model_id),None)


def health(rows,model_id,now=None):
    all_rows=[r for r in forward_window(rows,now) if prediction(r,model_id) is not None]
    selected=[r for r in all_rows if prediction(r,model_id)['selected'] and risk_score(r) is not None]
    regimes=[]
    for regime in ('trend_up','trend_down','range','high_volatility','mixed'):
        group=[r for r in selected if r.get('context',{}).get('regime')==regime]
        scores=[risk_score(r) for r in group];interval=daily_interval(group,scores)
        days=len({pd.Timestamp(r['exit_time']).tz_convert('Asia/Taipei').date() for r in group})
        supported=len(group)>=30 and days>=10 and interval[0] is not None and interval[0]>0
        avoid=len(group)>=30 and days>=10 and interval[1] is not None and interval[1]<0
        regimes.append({'regime':regime,'samples':len(group),'days':days,'mean_r':float(np.mean(scores)) if scores else None,
                        'interval95_r':interval,'state':'avoid' if avoid else 'supported' if supported else 'observe'})
    recent=selected[-30:];previous=selected[-90:-30]
    scores=[risk_score(r) for r in recent];interval=daily_interval(recent,scores)
    days=len({pd.Timestamp(r['exit_time']).tz_convert('Asia/Taipei').date() for r in recent})
    enough=len(recent)>=30 and len(previous)>=30 and days>=10
    def brier(group):
        pairs=[(prediction(r,model_id).get('probability'),float(r['pnl']>0)) for r in group]
        pairs=[(p,y) for p,y in pairs if p is not None and math.isfinite(p) and 0<=p<=1]
        return float(np.mean([(p-y)**2 for p,y in pairs])) if pairs else None
    br,bp=brier(recent),brier(previous)
    mean=float(np.mean(scores)) if scores else None
    old=float(np.mean([risk_score(r) for r in previous])) if previous else None
    reasons=[]
    if enough and interval[1] is not None and interval[1]<0:reasons.append('近期淨R群聚區間上限仍小於0')
    if enough and br is not None and bp is not None and br-bp>=.1 and mean<0 and mean<old:reasons.append('近期Brier誤差增加且淨R惡化')
    return {'model_id':model_id,'as_of':str(pd.Timestamp(now if now is not None else pd.Timestamp.now(tz='UTC'))),
            'status':'degraded' if reasons else 'monitoring' if enough else 'insufficient',
            'pause_qualified':bool(reasons),'reasons':reasons,'recent_samples':len(recent),'previous_samples':len(previous),
            'recent_days':days,'recent_mean_r':mean,'previous_mean_r':old,'recent_interval95_r':interval,
            'recent_brier':br,'previous_brier':bp,'recent_drawdown_r':r_drawdown(scores),'regimes':regimes,
            'note':'近90天最多200筆事前預測；近期30筆選擇交易對照之前最多60筆。未知不是健康保證，不修改原始模擬損益。'}


def reliability(rows,model_id,now=None):
    group=[]
    for r in forward_window(rows,now):
        p=prediction(r,model_id)
        if p and p.get('probability') is not None and math.isfinite(p['probability']) and 0<=p['probability']<=1:group.append((r,p))
    bins=[];error=0.
    for lo,hi in ((0,.2),(.2,.4),(.4,.6),(.6,.8),(.8,1.000001)):
        subset=[(r,p) for r,p in group if lo<=p['probability']<hi]
        if not subset:continue
        avg=float(np.mean([p['probability'] for r,p in subset]));observed=float(np.mean([r['pnl']>0 for r,p in subset]))
        error+=len(subset)*abs(avg-observed)
        bins.append({'分數區間':f'{lo:.1f}–{min(1,hi):.1f}','筆數':len(subset),'平均預測':avg,'觀察獲利比例':observed,'樣本足夠':len(subset)>=20})
    losses=[(p['probability']-float(r['pnl']>0))**2 for r,p in group]
    raw=[(p.get('raw_probability',p['probability'])-float(r['pnl']>0))**2 for r,p in group]
    return {'samples':len(group),'brier':float(np.mean(losses)) if losses else None,'raw_brier':float(np.mean(raw)) if raw else None,
            'ece':error/len(group) if group else None,'bins':bins,'calibrated_samples':sum(p.get('calibrated',False) for r,p in group),
            'note':'只使用當時保存的未來分數，分箱不足20筆不解讀成可靠勝率。Brier較低較好，校準不等於獲利改善。'}


def guard(rows,model_id,plan,now=None):
    report=health(rows,model_id,now)
    regime=plan.get('context',{}).get('regime')
    adaptation=next((r['state'] for r in report['regimes'] if r['regime']==regime),'observe')
    avoid=adaptation=='avoid'
    unfamiliar=adaptation=='observe'
    p=prediction(plan,model_id)
    blocked=report['pause_qualified'] or avoid or unfamiliar or bool(p and p.get('abstained'))
    return {'blocked':bool(blocked),'health':report['status'],'regime':regime,
            'reasons':report['reasons']+(['此行情的未來淨R證據為負'] if avoid else [])+(['此行情尚無足夠正向未來證據'] if unfamiliar else [])+(p.get('uncertainty',[]) if p else [])}
