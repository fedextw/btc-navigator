"""Separate the official persisted signal from unpromoted shadow research."""
import pandas as pd
from market_regime import classify
from market_data import INTERVALS


def explain(market,analysis,snapshot=None,walk=None,multi=None,now=None):
    now=pd.Timestamp(now or pd.Timestamp.now(tz='UTC'))
    regime=classify(market['candles'])
    same=False
    if snapshot:
        try:
            age=(now-pd.Timestamp(snapshot['updated_at'])).total_seconds()
            same=bool(0<=age<=240 and snapshot['symbol']==market['symbol'] and snapshot['interval']==market['interval']
                and snapshot['mode']==market['mode'] and pd.Timestamp(snapshot['candle_time'])==market['candles'].iloc[-1].close_time)
        except (KeyError,TypeError,ValueError):
            same=False
    gates=dict(snapshot.get('gates',{})) if same else {}
    gates['原背景門檻紀錄完整']=bool(same and snapshot.get('gates'))
    gates['背景快照新鮮且對應同根 K 線']=same
    gates['原研究時窗仍有效']=bool(0 <= (now-market['candles'].iloc[-1].close_time).total_seconds() < INTERVALS[market['interval']])
    formal=snapshot.get('side','WAIT') if same and market['mode']=='live' and analysis['valid'] and all(gates.values()) else 'WAIT'
    walk_matches=False
    if walk:
        try:
            walk_matches=bool(walk['symbol']==market['symbol'] and walk['interval']==market['interval']
                and walk['demo']==(market['mode']=='demo')
                and pd.Timestamp(walk['folds'][-1]['test_last_outcome'])<=market['candles'].iloc[-1].close_time
                and 0 <= (now-pd.Timestamp(walk['created_at'])).total_seconds() <= 7*86400)
        except (KeyError,IndexError,ValueError,TypeError):
            walk_matches=False
    shadow={'行情分類可用':regime['ready'],'非高波動環境':regime['code']!='high_volatility',
        '多週期資料完整':bool(multi and multi['complete']),
        '多週期與原研究方向一致':bool(multi and multi['side']==formal and formal!='WAIT'),
        '滾動報告對應幣種與基準時間':walk_matches,
        '滾動驗證通過研究檢驗':bool(walk_matches and walk.get('evidence_pass') and not walk.get('demo'))}
    blockers=[key for key,passed in gates.items() if not passed]
    if formal=='WAIT' and not blockers:
        blockers=['原規則／模型目前沒有合格方向']
    contrary=[f"{r['interval']}：{r['reason']}" for r in (multi or {}).get('rows',[]) if not r['valid']]
    if multi and multi['complete'] and multi['side']=='WAIT': contrary.append('三個週期分歧或 15m 尚未觸發方向')
    if regime['code']=='high_volatility': contrary.append('相對波動升高，歷史平均成本可能低估目前滑價')
    if not walk: contrary.append('尚無滾動驗證報告；不填補勝率或信心分數')
    elif not walk_matches: contrary.append('滾動報告與幣種、週期或基準時間不符，不納入判斷')
    stats=next((r for r in (walk if walk_matches else {}).get('regimes',[]) if r['code']==regime['code']),None)
    return {'formal_side':formal,'snapshot_matches':same,'formal_gates':gates,'regime':regime,
        'shadow_gates':shadow,'shadow_ready':all(shadow.values()),'blockers':blockers,'contrary':contrary,
        'regime_history':stats,'shadow_only':True,
        'invalidation':['新的 K 線收盤會重新評估；原訊號過期後不能沿用',
            '行情過期／缺口、規則與模型分歧、價格過度偏離時，原研究方向停止成立',
            '圖上 ATR 假設停損是風險參考，並不是已回測的出場成交策略']}
