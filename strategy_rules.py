"""Versioned, causal trend and intraday hypotheses, independent of the ML baseline."""
import hashlib
import numpy as np
import pandas as pd
from analysis_engine import indicators
from market_regime import regime_frame
from market_data import INTERVALS

PROFILES = {
 'trend': {'name':'趨勢單','version':'trend-pullback-v1','interval':'1h','higher':'4h','atr_stop':1.8,'reward_r':3.0,'max_bars':72,'max_stop_pct':8.0},
 'intraday': {'name':'短線當沖','version':'intraday-vwap-v1','interval':'15m','higher':'1h','atr_stop':1.2,'reward_r':1.8,'max_bars':8,'max_stop_pct':3.0},
}


def prepare(candles, higher):
    f=regime_frame(candles).copy()
    f['prior_high']=f.high.shift(1)
    f['prior_low20']=f.low.shift(1).rolling(20).min()
    f['prior_high20']=f.high.shift(1).rolling(20).max()
    f['swing_low']=f.low.rolling(5).min();f['swing_high']=f.high.rolling(5).max()
    f['recent_pull_long']=(f.low<=f.ema20+.3*f.atr).shift(1).rolling(5).max().fillna(0).astype(bool)
    f['recent_pull_short']=(f.high>=f.ema20-.3*f.atr).shift(1).rolling(5).max().fillna(0).astype(bool)
    f['prior_close']=f.close.shift(1)
    f['prior_low']=f.low.shift(1)
    session=f.time.dt.tz_convert('Asia/Taipei').dt.strftime('%Y-%m-%d')
    value=(f.high+f.low+f.close)/3*f.volume
    f['vwap']=value.groupby(session).cumsum()/f.volume.groupby(session).cumsum().replace(0,np.nan)
    f['session_bars']=f.groupby(session).cumcount()+1
    f['prior_vwap']=f.vwap.shift(1).where(session==session.shift(1))
    h=regime_frame(higher)
    h=h[['close_time','ema20','ema50','ema200','adx','regime','trend']].copy()
    h['higher_ready']=np.arange(len(h))>=199
    h=h.rename(columns={c:'higher_'+c for c in h.columns if c not in ('close_time','higher_ready')})
    h=h.rename(columns={'close_time':'higher_time'})
    f['close_time']=pd.to_datetime(f.close_time,utc=True).dt.as_unit('ns')
    h['higher_time']=pd.to_datetime(h.higher_time,utc=True).dt.as_unit('ns')
    return pd.merge_asof(f.sort_values('close_time'),h.sort_values('higher_time'),left_on='close_time',right_on='higher_time',direction='backward')


def resample_higher(candles, interval):
    seconds=INTERVALS[interval]
    indexed=candles.set_index('time')
    rule=f'{seconds}s'
    bars=indexed.resample(rule,origin='epoch',label='left',closed='left').agg(
        open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),volume=('volume','sum'))
    counts=indexed.close.resample(rule,origin='epoch',label='left',closed='left').count()
    step=(candles.time.iloc[1]-candles.time.iloc[0]).total_seconds()
    bars=bars[counts==int(seconds/step)].dropna().reset_index()
    bars['close_time']=bars.time+pd.Timedelta(seconds=seconds)-pd.Timedelta(milliseconds=1)
    return bars[bars.close_time<=candles.iloc[-1].close_time].reset_index(drop=True)


def candidate(row, profile, symbol, mode, fee_pct=.05,slippage_pct=.02):
    p=PROFILES[profile]
    def finite(key):
        try:return np.isfinite(float(row[key]))
        except (TypeError,ValueError,KeyError):return False
    ready=bool(row.get('higher_ready',False)==True and all(finite(k) for k in ('atr','rsi','macd_hist','vwap','higher_adx','higher_ema200')))
    age=(row.close_time-row.higher_time).total_seconds() if pd.notna(row.get('higher_time')) else float('inf')
    ready=ready and row.regime!='insufficient' and 0<=age<=INTERVALS[p['higher']]*1.5
    higher_side=row.get('higher_trend','WAIT')
    side=higher_side if higher_side in ('LONG','SHORT') else 'WAIT'
    long=side=='LONG'
    checks={'暖機與高週期資料完整':ready,'排除高波動與過渡環境':row.regime in ('trend_up','trend_down','range'),
            '高週期方向成立':side!='WAIT'}
    if profile=='trend':
        checks.update({'4h 趨勢強度至少20':finite('higher_adx') and row.higher_adx>=20,
            '1h EMA 排列與4h同向':row.trend==side and side!='WAIT',
            '回踩後突破前根高低':bool(row.recent_pull_long and row.close>row.prior_high) if long else bool(row.recent_pull_short and row.close<row.prior_low),
            'RSI與MACD同向':bool(50<=row.rsi<=72 and row.macd_hist>0) if long else bool(28<=row.rsi<=50 and row.macd_hist<0),
            '成交量至少近20根均量':bool(row.volume_ratio>=1)})
        setup='EMA20 回踩延續'
    else:
        reclaim=bool(row.prior_close<=row.prior_vwap and row.close>row.vwap and row.close>row.ema20) if long else bool(row.prior_close>=row.prior_vwap and row.close<row.vwap and row.close<row.ema20)
        sweep=bool(row.low<row.prior_low20 and row.close>row.prior_low20 and row.close>row.vwap) if long else bool(row.high>row.prior_high20 and row.close<row.prior_high20 and row.close<row.vwap)
        checks.update({'當日至少四根15m行情':bool(row.session_bars>=4),
            'VWAP收復或掃流動性收回':reclaim or sweep,
            'RSI與MACD同向':bool(50<=row.rsi<=68 and row.macd_hist>0) if long else bool(32<=row.rsi<=50 and row.macd_hist<0),
            '成交量至少均量1.1倍':bool(row.volume_ratio>=1.1)})
        setup='VWAP 收復' if reclaim else '流動性掃單收回'
    direction=1 if long else -1
    distance=max(float(row.atr)*p['atr_stop'],float(row.close-row.swing_low+.2*row.atr) if long else float(row.swing_high-row.close+.2*row.atr)) if finite('atr') else 0
    checks['停損距離有效']=bool(distance>0 and distance/row.close*100<=p['max_stop_pct'] and row.close-direction*distance>0)
    checks['目標幅度至少雙邊成本三倍']=bool(distance*p['reward_r']/row.close>=3*2*(fee_pct+slippage_pct)/100)
    qualified=all(checks.values())
    def number(key):return float(row[key]) if finite(key) else None
    vol=float(row.atr/row.close*100) if finite('atr') else None
    hour=pd.Timestamp(row.close_time).tz_convert('Asia/Taipei').hour
    context={'regime':row.regime,'setup':setup,'direction':side,
        'session':'台北00–08' if hour<8 else '台北08–16' if hour<16 else '台北16–24',
        'volatility':'低於0.5%' if vol is not None and vol<.5 else '0.5–1.5%' if vol is not None and vol<1.5 else '至少1.5%',
        'indicators':{k:number(k) for k in ('close','atr','rsi','macd_hist','volume_ratio','vwap','ema20','ema50','ema200','higher_adx')},
        'higher_candle':str(row.higher_time) if pd.notna(row.get('higher_time')) else None}
    signal_time=str(row.close_time)
    identity=hashlib.sha256(f'{p["version"]}/{symbol}/{mode}/{signal_time}'.encode()).hexdigest()[:24]
    return {'id':identity,'strategy':profile,'profile_version':p['version'],'symbol':symbol,'mode':mode,'interval':p['interval'],
        'signal_time':signal_time,'side':side if qualified else 'WAIT','proposed_side':side,'checks':{k:bool(v) for k,v in checks.items()},
        'reference':float(row.close),'stop':float(row.close-direction*distance) if qualified else None,
        'target':float(row.close+direction*distance*p['reward_r']) if qualified else None,
        'atr':number('atr'),'max_bars':p['max_bars'],'context':context,'paper_only':True}
