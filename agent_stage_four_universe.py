"""Read-only Binance USD-M active USDT perpetual contract discovery.

No trading credentials, private endpoints, or orders. Persist discovery
snapshots separately from any individual strategy research lineage.
"""
import argparse
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from agent_symbol_validation import valid_symbol

URL="https://fapi.binance.com/fapi/v1/exchangeInfo"
MAX_BODY=2_000_000

def discover(*,fetch=None,limit=10,offset=0,minimum_history_ms=0,now_ms=None):
    if type(limit) is not int or not 1<=limit<=10 or type(offset) is not int or offset<0:
        raise ValueError("Invalid bounded universe page")
    if type(minimum_history_ms) is not int or minimum_history_ms < 0:
        raise ValueError("Invalid minimum candle history")
    now_ms = int(datetime.now(timezone.utc).timestamp()*1000) if now_ms is None else now_ms
    request=fetch or urllib.request.urlopen
    with request(URL,timeout=20) as response:
        raw=response.read(MAX_BODY+1)
    if len(raw)>MAX_BODY:
        raise ValueError("Oversized exchange-info response")
    data=json.loads(raw)
    contracts=data.get("symbols") if isinstance(data,dict) else None
    if not isinstance(contracts,list) or len(contracts)>10000:
        raise ValueError("Invalid exchange-info contract list")
    eligible=[]
    for item in contracts:
        if not isinstance(item,dict):
            continue
        symbol=item.get("symbol")
        if (valid_symbol(symbol) and symbol==symbol.upper()
                and item.get("quoteAsset")=="USDT"
                and item.get("marginAsset")=="USDT"
                and item.get("contractType")=="PERPETUAL"
                and item.get("status")=="TRADING"
                and not (minimum_history_ms and type(item.get("onboardDate")) is int
                         and item["onboardDate"] > now_ms - minimum_history_ms)) :
            eligible.append(symbol)
    ready=sorted(set(eligible))
    batch=ready[offset:offset+limit]
    return {"schema":"agent-stage4-usdt-universe-v1","eligible_total":len(ready),
            "offset":offset,"limit":limit,"symbols":batch,
            "has_more":offset+limit<len(ready),
            "source":"binance_public_usdm_exchange_info",
            "paper_only":True,"live_trading_authorized":False}

def main():
    p=argparse.ArgumentParser(description="Read-only live USD-M USDT perpetual universe discovery")
    p.add_argument("--limit",type=int,default=10)
    p.add_argument("--offset",type=int,default=0)
    args=p.parse_args()
    print(json.dumps(discover(limit=args.limit,offset=args.offset),ensure_ascii=False,indent=2))
if __name__=="__main__":
    main()
