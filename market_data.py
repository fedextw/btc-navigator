"""Public market/news adapters. A failed live request never masquerades as live data."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import io
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
import requests

FUTURES = "https://fapi.binance.com"
INTERVALS = {"15m": 900, "1h": 3600, "4h": 14400}
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT")
FEEDS = {
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "Cointelegraph": "https://cointelegraph.com/rss",
    "Decrypt": "https://decrypt.co/feed",
}


def request_json(path, params=None):
    response = requests.get(FUTURES + path, params=params, timeout=(3, 7))
    response.raise_for_status()
    return response.json()


def validate_candles(rows, now=None):
    if not isinstance(rows, list) or len(rows) < 60:
        raise ValueError("行情不足 60 根 K 線")
    width = len(rows[0])
    frame = pd.DataFrame(rows).iloc[:, :7]
    frame.columns = ["time", "open", "high", "low", "close", "volume", "close_time"]
    if width >= 11:
        frame["quote_volume"] = [r[7] for r in rows]
        frame["taker_buy_quote"] = [r[10] for r in rows]
    for name in frame.columns:
        frame[name] = pd.to_numeric(frame[name], errors="raise")
    now = now or datetime.now(timezone.utc)
    frame = frame[frame.close_time < now.timestamp() * 1000].copy()
    if len(frame) < 60:
        raise ValueError("已收盤 K 線不足")
    if not np.isfinite(frame.to_numpy()).all():
        raise ValueError("行情包含非有限數值")
    if (frame[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("行情價格不正確")
    if "quote_volume" in frame and ((frame.quote_volume < 0) | (frame.taker_buy_quote < 0) | (frame.taker_buy_quote > frame.quote_volume)).any():
        raise ValueError("主動成交量不正確")
    if ((frame.high < frame[["open", "close", "low"]].max(axis=1)) |
            (frame.low > frame[["open", "close", "high"]].min(axis=1)) |
            (frame.volume < 0)).any():
        raise ValueError("OHLC 或成交量不正確")
    if not frame.time.is_monotonic_increasing or frame.time.duplicated().any():
        raise ValueError("K 線時間順序不正確")
    if (frame.close_time < frame.time).any():
        raise ValueError("K 線結束時間不正確")
    frame["time"] = pd.to_datetime(frame.time, unit="ms", utc=True)
    frame["close_time"] = pd.to_datetime(frame.close_time, unit="ms", utc=True)
    return frame.reset_index(drop=True)


def live_market(symbol, interval):
    if symbol not in SYMBOLS or interval not in INTERVALS:
        raise ValueError("不支援的交易對或週期")
    jobs = {
        "candles": ("/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": 300}),
        "premium": ("/fapi/v1/premiumIndex", {"symbol": symbol}),
        "oi": ("/futures/data/openInterestHist", {"symbol": symbol, "period": interval, "limit": 30}),
    }
    values, errors = {}, {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {key: pool.submit(request_json, *args) for key, args in jobs.items()}
        for key, future in futures.items():
            try:
                values[key] = future.result()
            except Exception as exc:
                errors[key] = type(exc).__name__
    if "candles" not in values:
        raise RuntimeError("Binance K 線連線失敗（網路政策、地區限制或上游服務異常）")
    frame = validate_candles(values["candles"])
    premium = values.get("premium", {})
    funding = None
    mark_price = None
    try:
        funding = float(premium["lastFundingRate"]) * 100
        mark_price = float(premium["markPrice"])
        if not np.isfinite(funding) or not np.isfinite(mark_price) or mark_price <= 0:
            raise ValueError("Invalid premium data")
    except (KeyError, TypeError, ValueError):
        errors["premium"] = "資金費率／標記價格不可用"
        funding = mark_price = None
    oi_usd = oi_change = None
    try:
        oi = values["oi"]
        first, last = float(oi[0]["sumOpenInterestValue"]), float(oi[-1]["sumOpenInterestValue"])
        if first <= 0 or last <= 0 or not np.isfinite([first, last]).all():
            raise ValueError("Invalid OI")
        oi_usd, oi_change = last, (last / first - 1) * 100
    except (KeyError, TypeError, ValueError, IndexError):
        errors["oi"] = "未平倉量不可用"
    return dict(candles=frame, funding=funding, oi_usd=oi_usd, oi_change=oi_change,
                mark_price=mark_price, mode="live", errors=errors, symbol=symbol, interval=interval,
                fetched_at=datetime.now(timezone.utc))


def demo_market(symbol, interval, count=300):
    """Deterministic synthetic data, explicitly tagged at every presentation boundary."""
    seed = int(hashlib.sha256((symbol + interval).encode()).hexdigest()[:8], 16)
    base = {"BTCUSDT": 68000, "ETHUSDT": 3400, "SOLUSDT": 145,
            "BNBUSDT": 590, "XRPUSDT": 0.62, "DOGEUSDT": 0.14}[symbol]
    seconds = INTERVALS[interval]
    end = pd.Timestamp.now(tz="UTC").floor(f"{seconds}s")
    times = pd.date_range(end=end - pd.Timedelta(seconds=seconds), periods=count, freq=f"{seconds}s")
    steps = times.as_unit("ns").astype("int64").to_numpy() / 1e9 / seconds
    def synthetic_price(t):
        return base * np.exp(.035 * np.sin(t / 25 + seed % 20) + .012 * np.sin(t / 7) +
                             .002 * np.sin(t * 12.9898 + seed % 100))
    close, opens = synthetic_price(steps), synthetic_price(steps - 1)
    noise = (np.sin(steps * 78.233 + seed % 100) + 1) / 2
    frame = pd.DataFrame({"time": times, "open": opens, "close": close,
                          "high": np.maximum(opens, close) * (1.001 + noise * .006),
                          "low": np.minimum(opens, close) * (.999 - (1 - noise) * .006),
                          "volume": 200 + noise * 2300,
                          "close_time": times + pd.Timedelta(seconds=seconds) - pd.Timedelta(milliseconds=1)})
    frame["quote_volume"] = frame.volume * frame.close
    frame["taker_buy_quote"] = frame.quote_volume * (.5 + .12 * np.sin(steps / 9))
    return dict(candles=frame, funding=0.012, oi_usd=8_320_000_000,
                oi_change=3.7, mark_price=float(close[-1]), mode="demo", errors={},
                symbol=symbol, interval=interval, fetched_at=datetime.now(timezone.utc))


def load_market(symbol, interval, mode="auto"):
    if mode == "demo":
        return demo_market(symbol, interval)
    try:
        return live_market(symbol, interval)
    except (RuntimeError, ValueError, requests.RequestException) as exc:
        if mode == "live":
            raise RuntimeError(str(exc)) from exc
        result = demo_market(symbol, interval)
        result["errors"]["live"] = str(exc)
        return result


def fetch_feed(source, url):
    response = requests.get(url, timeout=(3, 7), headers={"User-Agent": "BTCNavigator/1.0 RSS reader"})
    response.raise_for_status()
    if len(response.content) > 2_000_000:
        raise ValueError("RSS 超出大小限制")
    root = ET.fromstring(response.content)
    articles = []
    for item in root.findall(".//item")[:10]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if title and link.startswith("https://"):
            articles.append(dict(title=title, url=link, source=source,
                                 published=(item.findtext("pubDate") or "時間未提供")))
    return articles


def load_news():
    articles, errors = [], []
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {source: pool.submit(fetch_feed, source, url) for source, url in FEEDS.items()}
        for source, future in jobs.items():
            try:
                articles.extend(future.result())
            except (requests.RequestException, ValueError, ET.ParseError):
                errors.append(source)
    # Interleave each feed's latest entries without claiming publication-time order.
    articles = [article for _, article in sorted(enumerate(articles), key=lambda pair: pair[0] % 10)]
    seen, unique = set(), []
    for article in articles:
        if article["url"] not in seen:
            seen.add(article["url"])
            unique.append(article)
    return unique, errors


def load_history(symbol, interval, demo=False):
    if symbol not in SYMBOLS or interval not in INTERVALS:
        raise ValueError("不支援的交易對或週期")
    if demo:
        return demo_market(symbol, interval, count=1500)["candles"]
    rows = request_json("/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": 1500})
    return validate_candles(rows)


def import_history_csv(content, interval):
    """Import OHLCV, never synthesize missing market prices."""
    if len(content) > 2_000_000:
        raise ValueError("CSV 上限 2 MB")
    frame = pd.read_csv(io.BytesIO(content))
    if not 800 <= len(frame) <= 5000:
        raise ValueError("CSV 需含 800～5,000 根 K 線")
    required = ["time", "open", "high", "low", "close", "volume"]
    if not set(required).issubset(frame.columns):
        raise ValueError("CSV 必須包含 time,open,high,low,close,volume 欄位")
    if pd.api.types.is_numeric_dtype(frame.time):
        times = pd.to_datetime(frame.time, unit="ms", utc=True)
    else:
        times = pd.to_datetime(frame.time, utc=True)
    close_time = times + pd.Timedelta(seconds=INTERVALS[interval]) - pd.Timedelta(milliseconds=1)
    rows = [[int(t.timestamp() * 1000), row.open, row.high, row.low, row.close, row.volume,
             int(c.timestamp() * 1000)] for t, c, row in zip(times, close_time, frame.itertuples())]
    return validate_candles(rows)
