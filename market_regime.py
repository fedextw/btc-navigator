"""Causal, fixed-rule market regimes. Descriptive labels, not fitted probabilities."""
import numpy as np
import pandas as pd
from analysis_engine import indicators

LABELS = {'trend_up':'上升趨勢','trend_down':'下降趨勢','range':'區間盤整',
          'high_volatility':'高波動','mixed':'過渡／分歧','insufficient':'資料不足'}


def regime_frame(candles):
    frame = indicators(candles)
    up, down = frame.high.diff(), -frame.low.diff()
    plus = up.where((up > down) & (up > 0), 0.0)
    minus = down.where((down > up) & (down > 0), 0.0)
    frame['plus_di'] = 100 * plus.ewm(alpha=1/14,adjust=False,min_periods=14).mean()/frame.atr.replace(0,np.nan)
    frame['minus_di'] = 100 * minus.ewm(alpha=1/14,adjust=False,min_periods=14).mean()/frame.atr.replace(0,np.nan)
    denom = (frame.plus_di + frame.minus_di).replace(0,np.nan)
    dx = (100*(frame.plus_di-frame.minus_di).abs()/denom).fillna(0)
    frame['adx'] = dx.ewm(alpha=1/14,adjust=False,min_periods=28).mean()
    frame['atr_pct'] = frame.atr/frame.close*100
    # No centered windows, backfill, or full-history percentiles.
    frame['atr_baseline'] = frame.atr_pct.rolling(100,min_periods=100).median()
    path = frame.close.diff().abs().rolling(30).sum()
    frame['efficiency'] = (frame.close-frame.close.shift(30)).abs()/path.replace(0,np.nan)
    frame['efficiency'] = frame.efficiency.where(path != 0,0)
    uptrend = (frame.ema20 > frame.ema50) & (frame.ema50 > frame.ema200) & (frame.ema50 > frame.ema50.shift(20))
    downtrend = (frame.ema20 < frame.ema50) & (frame.ema50 < frame.ema200) & (frame.ema50 < frame.ema50.shift(20))
    ready = (np.arange(len(frame)) >= 199) & frame[['adx','atr_pct','atr_baseline','efficiency']].notna().all(axis=1)
    frame['trend'] = np.select([uptrend,downtrend],['LONG','SHORT'],default='WAIT')
    frame['regime'] = np.select([
        ~ready, frame.atr_pct > frame.atr_baseline*1.5,
        (frame.adx>=25)&uptrend,(frame.adx>=25)&downtrend,
        (frame.adx<20)&(frame.efficiency<.35)],
        ['insufficient','high_volatility','trend_up','trend_down','range'],default='mixed')
    frame.loc[~ready,'trend']='WAIT'
    return frame


def classify(candles):
    if candles.empty:
        return {'code':'insufficient','label':LABELS['insufficient'],'trend':'WAIT','ready':False}
    row=regime_frame(candles).iloc[-1]
    code=row.regime
    def number(key):
        value=float(row[key])
        return value if np.isfinite(value) else None
    return {'code':code,'label':LABELS[code],'trend':row.trend,'ready':code!='insufficient',
            'adx':number('adx'),'atr_pct':number('atr_pct'),'efficiency':number('efficiency'),
            'as_of':str(row.close_time), 'method':'固定描述規則；ADX 25／20、ATR 相對中位數 1.5×，未經策略效果驗證'}
