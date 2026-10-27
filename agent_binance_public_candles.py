"""Fetch public Binance USD-M perpetual market candles for offline paper research.

No account API credentials, signed endpoints, broker state, or order endpoints.
Downloads historical closed candles only; page boundaries checked strictly.
"""
import argparse
import csv
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from agent_csv_research import read_candles

BASE="https://fapi.binance.com/fapi/v1/klines"
INTERVALS={"1m","5m","15m","1h","4h","1d"}

def download_public_candles(path, *, symbol="BTCUSDT", interval="1h", count=1600,
                            fetch=None):
    if not isinstance(symbol,str) or not re.fullmatch(r"[A-Z0-9]{2,25}USDT",symbol):
        raise ValueError("Invalid USDT perpetual symbol")
    if interval not in INTERVALS or type(count) is not int or not 300 <= count <= 3000:
        raise ValueError("Invalid candle interval or bounded count")
    path=Path(path)
    if path.exists():
        raise FileExistsError("Research snapshot already exists")
    request=fetch if fetch is not None else urllib.request.urlopen
    rows=[]
    # End the initial page at least one full interval in the past.\n    # This prevents selecting the actively forming candle.\n    interval_ms={"1m":60000,"5m":300000,"15m":900000,"1h":3600000,\n                 "4h":14400000,"1d":86400000}[interval]\n    end=int(datetime.now(timezone.utc).timestamp()*1000)-interval_ms\n    # Binance endpoint provides at most 1500 candles per response.
    while len(rows)<count:
        size=min(1000,count-len(rows))
        query={"symbol":symbol,"interval":interval,"limit":size}
        if end is not None:
            query["endTime"]=end
        url=BASE+"?"+urllib.parse.urlencode(query)
        with request(url,timeout=20) as response:
            payload=json.loads(response.read(3_000_000))
        if not isinstance(payload,list) or len(payload)!=size:
            raise ValueError("Incomplete Binance candle response")
        batch=[]
        for item in payload:
            if not isinstance(item,list) or len(item)<7:
                raise ValueError("Malformed Binance candle")
            start_ms=int(item[0])
            close_ms=int(item[6])
            if start_ms>close_ms:
                raise ValueError("Invalid candle bounds")
            batch.append((start_ms,close_ms,item))
        if any(batch[i][0]>=batch[i+1][0] for i in range(len(batch)-1)):
            raise ValueError("Unsorted Binance candles")
        if rows and batch[-1][0]>=rows[0][0]:
            raise ValueError("Overlapping Binance candle pages")
        rows=batch+rows
        end=batch[0][0]-1
    # Exclude latest still-forming bar using Binance close times and local UTC.
    now_ms=int(datetime.now(timezone.utc).timestamp()*1000)
    if any(close_ms>=now_ms for _,close_ms,_ in rows):
        raise ValueError("Binance response contains open/future candle")
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    try:
        with tmp.open("x",encoding="utf-8",newline="") as file:
            writer=csv.writer(file,lineterminator="\n")
            writer.writerow(("time","open","high","low","close","volume"))
            for open_ms,_,item in rows:
                writer.writerow((datetime.fromtimestamp(open_ms/1000,timezone.utc).isoformat(),
                                 item[1],item[2],item[3],item[4],item[5]))
        checked,digest=read_candles(tmp)
        if len(checked)!=count:
            raise ValueError("Wrong candle count")
        tmp.rename(path)
    finally:
        tmp.unlink(missing_ok=True)
    return {"csv":str(path),"symbol":symbol,"interval":interval,"candles":count,
            "dataset_sha256":digest,"public_data_only":True}

def main():
    parser=argparse.ArgumentParser(description="Binance public USD-M candle snapshot")
    parser.add_argument("--out",required=True)
    parser.add_argument("--symbol",default="BTCUSDT")
    parser.add_argument("--interval",default="1h")
    parser.add_argument("--count",type=int,default=1600)
    args=parser.parse_args()
    print(json.dumps(download_public_candles(args.out,symbol=args.symbol,
                    interval=args.interval,count=args.count),ensure_ascii=False))
if __name__=="__main__":
    main()
