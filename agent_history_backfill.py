"""Opt-in bounded historical candle backfill for B+C research.

Never trades, never modifies existing candles, never manufactures missing data.
Only fills one requested symbol/interval from exchange public candles per call.
"""
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import sqlite3
import time

from agent_symbol_validation import valid_symbol
from agent_research_universe import SECONDS, contiguous_utc

def backfill_once(state_dir, symbol, interval="1h", client=None, now=None):
    if not valid_symbol(symbol) or interval not in SECONDS:
        raise ValueError("研究補資料參數不合法")
    root=Path(state_dir).resolve()
    database=root/"research.sqlite3"
    if not database.is_file():
        return {"status":"waiting_database","inserted":0,"live_trading_authorized":False}
    if client is None:
        from binance_client import BinanceClient
        client=BinanceClient()
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset().total_seconds()!=0:
        raise ValueError("現在時間必須為 UTC")
    # 500 bars per call is bounded. Fetch includes latest open bar, filtered below.
    payload=client.json("/fapi/v1/klines",
                        params={"symbol":symbol,"interval":interval,"limit":500},weight=2)
    if not isinstance(payload,list) or len(payload)>500:
        raise ValueError("交易所 K 棒回傳格式異常")
    accepted=[]
    for row in payload:
        if not isinstance(row,(list,tuple)) or len(row)<7:
            raise ValueError("K 棒欄位不足")
        start_ms=int(row[0]);end_ms=int(row[6])
        if start_ms<0 or end_ms<=start_ms:
            raise ValueError("K 棒時間不正確")
        if end_ms>=now.timestamp()*1000:
            continue
        prices=[float(row[i]) for i in (1,2,3,4,5)]
        o,h,l,c,v=prices
        if min(o,h,l,c)<=0 or v<0 or h<max(o,c,l) or l>min(o,c,h):
            raise ValueError("K 棒數值異常")
        from math import isfinite
        if not all(isfinite(p) for p in prices):
            raise ValueError("K 棒數值非有限")
        start=datetime.fromtimestamp(start_ms/1000,timezone.utc)
        end=datetime.fromtimestamp(end_ms/1000,timezone.utc)
        accepted.append((symbol,interval,"live",start.isoformat(),end.isoformat(),o,h,l,c,v))
    accepted.sort(key=lambda item:item[3])
    if len(set(row[3] for row in accepted))!=len(accepted):
        raise ValueError("K 棒重複時間")
    if accepted and not contiguous_utc([(row[3],) for row in reversed(accepted[-300:])],interval) and len(accepted)>=300:
        raise ValueError("交易所最近 K 棒存在缺口")
    with closing(sqlite3.connect(database,timeout=5)) as db:
        # Only insert absent rows. Running scanner's candles remain authoritative.
        db.execute("BEGIN IMMEDIATE")
        before=db.total_changes
        db.executemany("INSERT OR IGNORE INTO candles "
                       "(symbol,interval,mode,time,close_time,open,high,low,close,volume) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?)",accepted)
        inserted=db.total_changes-before
        db.commit()
    return {"status":"completed","symbol":symbol,"interval":interval,
            "received":len(accepted),"inserted":inserted,"live_trading_authorized":False}

def main():
    p=argparse.ArgumentParser(description="選用的單幣種公開行情補資料（限額，無交易）")
    p.add_argument("--state-dir",required=True)
    p.add_argument("--symbol",required=True)
    p.add_argument("--interval",choices=tuple(SECONDS),default="1h")
    a=p.parse_args()
    print(json.dumps(backfill_once(a.state_dir,a.symbol,a.interval),ensure_ascii=False))

if __name__=="__main__":
    main()
