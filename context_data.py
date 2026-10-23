"""Public market context with provenance; supply and TVL are not net inflows."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import math
import requests

SOURCES = {
    "CoinGecko": "https://api.coingecko.com/api/v3/global",
    "DefiLlama Stablecoins": "https://stablecoins.llama.fi/stablecoincharts/all",
    "DefiLlama TVL": "https://api.llama.fi/v2/historicalChainTvl",
    "Alternative.me": "https://api.alternative.me/fng/?limit=7",
}


def get_json(url):
    response = requests.get(url, timeout=(3, 8), headers={"User-Agent": "BTCNavigator/1.0 public research"})
    response.raise_for_status()
    if len(response.content) > 3_000_000:
        raise ValueError("公開資料超出大小限制")
    return response.json()


def number(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Nonfinite public data")
    return result


def parse_context(source, payload):
    if source == "CoinGecko":
        row = payload["data"]
        return {"market_cap_usd": number(row["total_market_cap"]["usd"]),
                "volume_24h_usd": number(row["total_volume"]["usd"]),
                "btc_dominance_pct": number(row["market_cap_percentage"]["btc"]),
                "market_cap_change_24h_pct": number(row["market_cap_change_percentage_24h_usd"]),
                "as_of": datetime.fromtimestamp(int(row["updated_at"]), timezone.utc).isoformat()}
    if source.startswith("DefiLlama"):
        rows = sorted(payload, key=lambda r: int(r["date"]))
        if len(rows) < 8:
            raise ValueError("歷史資料不足")
        key = "stablecoin_supply_usd" if "Stablecoins" in source else "tvl_usd"
        def amount(row):
            return number(row["totalCirculating"]["peggedUSD"] if "Stablecoins" in source else row["tvl"])
        current, previous = amount(rows[-1]), amount(rows[-8])
        if previous <= 0 or current <= 0:
            raise ValueError("總量不正確")
        return {key: current, "change_7_samples_pct": (current / previous - 1) * 100,
                "as_of": datetime.fromtimestamp(int(rows[-1]["date"]), timezone.utc).isoformat(),
                "comparison_as_of": datetime.fromtimestamp(int(rows[-8]["date"]), timezone.utc).isoformat()}
    row = payload["data"][0]
    value = int(row["value"])
    if not 0 <= value <= 100:
        raise ValueError("情緒指數範圍不正確")
    return {"fear_greed": value, "classification": str(row["value_classification"]),
            "as_of": datetime.fromtimestamp(int(row["timestamp"]), timezone.utc).isoformat()}


def load_context():
    data, errors = {}, {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {name: pool.submit(get_json, url) for name, url in SOURCES.items()}
        for source, future in jobs.items():
            try:
                values = parse_context(source, future.result())
                values["source_url"] = SOURCES[source]
                values["stale"] = (datetime.now(timezone.utc) - datetime.fromisoformat(values["as_of"])).total_seconds() > 3 * 86400
                data[source] = values
            except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
                errors[source] = "目前無法取得或驗證資料"
    return {"data": data, "errors": errors, "fetched_at": datetime.now(timezone.utc).isoformat()}
