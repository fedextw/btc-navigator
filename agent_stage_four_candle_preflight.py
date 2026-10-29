"""Public-data-only candle history eligibility before model-call reservation."""
import json
import argparse
import urllib.parse
import urllib.request
import tempfile
from pathlib import Path
from agent_binance_public_candles import download_public_candles
from datetime import datetime, timezone

INTERVAL_MS={"15m":900000,"1h":3600000,"4h":14400000}
BASE="https://fapi.binance.com/fapi/v1/klines"

def enough_closed_history(symbol, *, interval="1h", count=1600, fetch=None, now_ms=None, verify_full_window=False):
    if interval not in INTERVAL_MS or type(count) is not int or count<100:
        raise ValueError("Invalid history preflight parameters")
    now=int(datetime.now(timezone.utc).timestamp()*1000) if now_ms is None else now_ms
    url=BASE+"?"+urllib.parse.urlencode({"symbol":symbol,"interval":interval,
                                          "startTime":0,"limit":1})
    with (fetch or urllib.request.urlopen)(url,timeout=20) as response:
        raw=response.read(20000)
    data=json.loads(raw)
    if not isinstance(data,list):
        raise ValueError("Invalid historical candle response")
    if not data:
        return False
    if not isinstance(data[0],list) or len(data[0])<7:
        raise ValueError("Malformed historical candle")
    earliest=int(data[0][0])
    last_closed_start=(now//INTERVAL_MS[interval]-1)*INTERVAL_MS[interval]
    if earliest+(count-1)*INTERVAL_MS[interval]>last_closed_start:
        return False
    if not verify_full_window:
        return True
    # Listing age is NOT proof of an uninterrupted 1,600-candle window.
    # Exercise the exact public downloader before any model-call reservation.
    with tempfile.TemporaryDirectory(prefix="bc-candle-check-") as directory:
        try:
            download_public_candles(Path(directory)/"market.csv",
                symbol=symbol, interval=interval, count=count, fetch=fetch)
        except ValueError as exc:
            # A short historical window must not reserve a potentially paid
            # research slot. Unexpected corruption/errors are not suppressed.
            if str(exc) in ("Incomplete Binance candle response",
                            "Wrong candle count"):
                return False
            raise
    return True

def main():
    parser=argparse.ArgumentParser(description="Public Binance history preflight only; zero OpenAI calls")
    parser.add_argument("--symbol",default="4USDT")
    parser.add_argument("--interval",choices=tuple(INTERVAL_MS),default="1h")
    parser.add_argument("--count",type=int,default=1600)
    args=parser.parse_args()
    try:
        sufficient=enough_closed_history(args.symbol,interval=args.interval,
                                          count=args.count,verify_full_window=True)
        result={"symbol":args.symbol,"status":"ready" if sufficient else "insufficient_history",
                "openai_calls":0,"paper_only":True}
    except Exception as exc:
        result={"symbol":args.symbol,"status":"public_data_error",
                "error_type":type(exc).__name__,
                "openai_calls":0,"paper_only":True}
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result["status"]=="ready" else 1

if __name__=="__main__":
    raise SystemExit(main())
