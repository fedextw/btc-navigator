"""Bounded public-data reads for an explicit interactive research session."""
import json
from pathlib import Path
import pandas as pd
from binance_client import BinanceClient
from market_data import demo_market, validate_candles, valid_symbol, INTERVALS
from runtime_config import STATE_ROOT

CLIENT=BinanceClient()


def load_bundle(symbol,mode='live',root=STATE_ROOT):
    if not valid_symbol(symbol) or mode not in ('live','demo'):
        raise ValueError('交易對或資料模式不正確')
    markets={}; errors={}
    for interval in ('15m','1h','4h'):
        try:
            if mode=='demo':
                markets[interval]=demo_market(symbol,interval)
                continue
            # Reuse the worker's fresh closed-candle cache when available.
            frame=None
            path=Path(root)/'signals.sqlite3'
            if path.exists():
                import sqlite3
                with sqlite3.connect(f'file:{path}?mode=ro',uri=True,timeout=5) as db:
                    row=db.execute('SELECT payload FROM scan_cache WHERE symbol=? AND interval=? AND mode=?',(symbol,interval,mode)).fetchone()
                if row:
                    cached=pd.DataFrame(json.loads(row[0]))
                    cached['time']=pd.to_datetime(cached.time,utc=True)
                    cached['close_time']=pd.to_datetime(cached.close_time,utc=True)
                    expected=(pd.Timestamp.now(tz='UTC')-pd.Timedelta(seconds=5)).floor(f'{INTERVALS[interval]}s')-pd.Timedelta(milliseconds=1)
                    if cached.iloc[-1].close_time>=expected:
                        frame=cached
            if frame is None:
                frame=validate_candles(CLIENT.json('/fapi/v1/klines',{'symbol':symbol,'interval':interval,'limit':300},weight=2))
            markets[interval]={'symbol':symbol,'interval':interval,'mode':mode,'candles':frame,
                'funding':None,'mark_price':None,'oi_change':None,'errors':{}}
        except Exception as exc:
            from binance_client import BinanceAccessError, RatePause
            errors[interval]=str(exc) if isinstance(exc,(BinanceAccessError,RatePause)) else type(exc).__name__
    return markets,errors


def history(symbol,interval,mode='live'):
    if not valid_symbol(symbol) or interval not in INTERVALS or mode not in ('live','demo'):
        raise ValueError('歷史研究參數不正確')
    if mode=='demo':
        return demo_market(symbol,interval,1500)['candles']
    return validate_candles(CLIENT.json('/fapi/v1/klines',{'symbol':symbol,'interval':interval,'limit':1500},weight=10))
