"""Descriptive post-trade evidence, not causal claims or hindsight parameter tuning."""
import math
import pandas as pd

LABELS={'cost_flip':'成本使正向價格損益轉負','adverse_exit':'出場價格逆向','entry_gap':'不利開盤偏移至少0.25ATR',
        'giveback':'曾有至少1R有利價格後虧損','gap_stop':'跳空停損','ambiguous_bar':'同根同觸，按停損優先',
        'time_exit':'到期／當沖日界出場','incomplete_path':'持倉路徑觀察不完整'}


def track_excursion(t,bar,raw_exit=None):
    if 'mfe_usdt' not in t:
        t.update(mfe_usdt=0.,mae_usdt=0.,excursion_complete=False,excursion_start_at=str(bar.time))
    direction=1 if t['side']=='LONG' else -1
    # The exit bar's high/low may occur after exit: never use its full range.
    prices=[raw_exit] if raw_exit is not None else [bar.high,bar.low]
    moves=[direction*t['quantity']*(float(p)-t['entry']) for p in prices]
    t['mfe_usdt']=max(t['mfe_usdt'],max(moves),0.)
    t['mae_usdt']=max(t['mae_usdt'],-min(moves),0.)
    t['excursion_basis']='完整存續K線＋模擬出場點；未使用出場根全部高低'


def review(t):
    if t.get('status')!='closed':return {'version':'review-v1','status':'尚未結算','tags':[],'bridge':None}
    direction=1 if t['side']=='LONG' else -1
    tags=[];facts=[];bridge=None
    required=('raw_entry','raw_exit','entry','exit','quantity','fees','funding','pnl')
    if all(t.get(k) is not None and math.isfinite(float(t[k])) for k in required):
        q=t['quantity'];price_pnl=direction*q*(t['raw_exit']-t['raw_entry'])
        slippage=direction*q*((t['entry']-t['raw_entry'])+(t['raw_exit']-t['exit']))
        reconciled=price_pnl-slippage-t['fees']-t['funding']
        bridge={'原始價格損益':price_pnl,'滑價損失':slippage,'手續費':t['fees'],'資金費支出':t['funding'],'重建淨損益':reconciled,'原紀錄淨損益':t['pnl'],'差額':reconciled-t['pnl']}
        if price_pnl>0 and t['pnl']<0:tags.append('cost_flip')
        if price_pnl<0:tags.append('adverse_exit')
        gap=direction*(t['raw_entry']-t['reference'])
        if t.get('atr',0)>0 and gap>=.25*t['atr']:tags.append('entry_gap')
        facts.append('開盤相對參考價偏移 '+str(round(gap,8)))
    else:facts.append('缺少原始成交價格，不能精確拆分滑價與價格損益；不回填舊交易。')
    reason=t.get('exit_reason','')
    if reason=='stop_gap':tags.append('gap_stop')
    if reason=='stop_both_hit':tags.append('ambiguous_bar')
    if reason in ('time_limit','session_close'):tags.append('time_exit')
    if not t.get('excursion_complete',False):tags.append('incomplete_path')
    elif t.get('pnl',0)<0 and t.get('risk_budget',0)>0 and t.get('mfe_usdt',0)>=t['risk_budget']:tags.append('giveback')
    return {'version':'review-v1','status':'描述性復盤','tags':tags,'facts':facts,'bridge':bridge,
            'mfe_r':t.get('mfe_usdt',0)/t['risk_budget'] if t.get('risk_budget',0)>0 and 'mfe_usdt' in t else None,
            'mae_r':t.get('mae_usdt',0)/t['risk_budget'] if t.get('risk_budget',0)>0 and 'mae_usdt' in t else None,
            'path_complete':bool(t.get('excursion_complete')),
            'note':'標籤可重疊，是已觀測現象，不證明方向、止損或進場參數有錯；不推論出場後行情，不自動改策略。'}
