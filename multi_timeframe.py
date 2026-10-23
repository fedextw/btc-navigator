"""Point-in-time closed-candle alignment. Never mix live and demo evidence."""
import pandas as pd
from analysis_engine import analyze
from market_data import INTERVALS
from market_regime import classify

PERIODS = ('4h','1h','15m')
ROLES = {'4h':'大方向','1h':'交易條件','15m':'時機觀察'}


def compare(markets, as_of, expected_mode='live'):
    as_of=pd.Timestamp(as_of)
    if as_of.tzinfo is None:
        raise ValueError('研究基準時間必須包含時區')
    rows=[]
    symbols={m['symbol'] for m in markets.values()}
    if len(symbols)>1:
        raise ValueError('不能混合不同交易對的週期')
    for interval in PERIODS:
        market=markets.get(interval)
        row={'interval':interval,'role':ROLES[interval],'valid':False,'trend':'WAIT','rule_side':'WAIT',
             'score':None,'regime':'資料不足','candle_time':None,'reason':'尚無該週期行情'}
        if market:
            if market.get('mode')!=expected_mode or market.get('interval')!=interval:
                row['reason']='來源模式或週期不一致，不納入共識'
            else:
                candles=market['candles']
                visible=candles[candles.close_time<=as_of].copy()
                if len(visible)>=200:
                    # Funding is current context, not a point-in-time historical feature.
                    aligned={**market,'candles':visible,'funding':None,'oi_change':None}
                    analysis=analyze(aligned,now=as_of)
                    regime=classify(visible)
                    valid=analysis['valid'] and regime['ready']
                    row.update(valid=bool(valid),trend=regime['trend'],rule_side=analysis['side'],score=analysis['score'],
                        regime=regime['label'],regime_code=regime['code'],adx=regime.get('adx'),atr_pct=regime.get('atr_pct'),
                        candle_time=str(visible.iloc[-1].close_time),
                        reason='已按基準時間對齊' if valid else '行情過期、缺口或指標不足')
                else:
                    row['reason']='基準時間前不足 200 根已收盤 K 線'
        rows.append(row)
    complete=all(row['valid'] for row in rows)
    directions={row['trend'] for row in rows}
    direction=next(iter(directions)) if complete and len(directions)==1 and 'WAIT' not in directions else 'WAIT'
    # Timing requires a directional rule on the shortest period, not just EMA ordering.
    if direction!='WAIT' and rows[-1]['rule_side']!=direction:
        direction='WAIT'
    return {'as_of':str(as_of),'mode':expected_mode,'rows':rows,'complete':complete,'side':direction,
            'status':'三週期同向' if direction!='WAIT' else '分歧／觀望' if complete else '資料不足',
            'shadow_only':True,'note':'4h／1h／15m 趨勢同向且 15m 規則同向才成立；研究條件不是勝率，未改寫原訊號。'}
