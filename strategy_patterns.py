"""Exploratory, prespecified cohorts with a purged chronological confirmation set."""
import hashlib
import json
import pandas as pd
from learning_lab import trade_stats

FIELDS=('regime','setup','session','volatility','direction')


def discover(rows,mode):
    rows=sorted([r for r in rows if r.get('status')=='closed' and r.get('source')!='historical_replay'],key=lambda r:(pd.Timestamp(r['created_at']),r['id']))
    report={'samples':len(rows),'patterns':[],'mode':mode,'created_at':str(pd.Timestamp.now(tz='UTC')),
        'note':'探索性規律，未校正多重比較；每日重看確認集可能產生選擇偏誤，不自動修改策略或保證勝率'}
    if len(rows)<60:report['status']='至少60筆未來結算紀錄才探索規律';return report
    boundary=pd.Timestamp(rows[int(len(rows)*.6)]['created_at'])
    train=[r for r in rows if pd.Timestamp(r['created_at'])<boundary and max(pd.Timestamp(r['exit_time']),pd.Timestamp(r.get('settled_at',r['exit_time'])))<boundary]
    confirmation=[r for r in rows if pd.Timestamp(r['created_at'])>=boundary]
    report.update(boundary=str(boundary),discovery_samples=len(train),confirmation_samples=len(confirmation))
    base=trade_stats(confirmation)
    for field in FIELDS:
        for value in sorted({str(r.get('context',{}).get(field,'未知')) for r in train}):
            a=[r for r in train if str(r.get('context',{}).get(field,'未知'))==value]
            b=[r for r in confirmation if str(r.get('context',{}).get(field,'未知'))==value]
            x,y=trade_stats(a),trade_stats(b)
            supported=bool(mode=='live' and len(a)>=20 and len(b)>=10 and x['expectancy_pct'] is not None and x['expectancy_pct']>0
                and y['expectancy_pct'] is not None and y['expectancy_pct']>0 and y['profit_factor'] is not None and y['profit_factor']>=1.1
                and base['expectancy_pct'] is not None and y['expectancy_pct']>base['expectancy_pct'])
            report['patterns'].append({'feature':field,'value':value,'discovery':x,'confirmation':y,'exploratory_support':supported})
    report['status']='探索完成，需新的後續樣本驗證'
    report['id']=hashlib.sha256(json.dumps([(r['id'],r['pnl']) for r in rows]).encode()).hexdigest()[:20]
    return report
