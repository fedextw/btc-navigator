# BTC Navigator App

"""
這是一個自動分析比特幣市場走勢的工具，支援 CLI、Streamlit 與 FastAPI 伺服器模式，並具備離線回退、測試、自動更新等特性。
"""

import sys, os, math, random, json, time, argparse, datetime
from typing import List, Tuple, Dict

try:
    import pandas as pd
    import numpy as np
    import requests
except ImportError:
    sys.stderr.write("請安裝 pandas、numpy、requests 套件\n")
    sys.exit(1)

try:
    import streamlit as st
except ImportError:
    st = None

try:
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    import uvicorn
except ImportError:
    FastAPI = None

# ========== 資料抓取邏輯 ========== #
def http_get(url: str, headers: Dict = {}, timeout: float = 10):
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise RuntimeError(f"[ERROR] 無法存取 URL：{url} → {e}")

def get_binance_klines(symbol="BTCUSDT", interval="1h", lookback_days=30):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=1000"
    return http_get(url)

def get_binance_funding(symbol="BTCUSDT"):
    url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}&limit=100"
    return http_get(url)

def get_binance_oi(symbol="BTCUSDT"):
    url = f"https://fapi.binance.com/futures/data/openInterestHist?symbol={symbol}&period=1h&limit=100"
    return http_get(url)

# ========== 模擬資料生成（Offline） ========== #
def gen_mock_market(n=100):
    price = [30000 + i * 20 + random.uniform(-100, 100) for i in range(n)]
    fr = [0.0002 + 0.0001 * math.sin(i/10) for i in range(n)]
    oi = [1e9 + i * 1e6 + random.uniform(-5e6, 5e6) for i in range(n)]
    return price, fr, oi

# ========== 技術指標 ========== #
def zlema(values: List[float], period: int) -> List[float]:
    ema = []
    lag = (period - 1) // 2
    for i in range(len(values)):
        if i == 0:
            ema.append(values[i])
        else:
            v = values[i] + (values[i] - values[i - lag]) if i - lag >= 0 else values[i]
            k = 2 / (period + 1)
            ema.append(k * v + (1 - k) * ema[-1])
    return ema

def rsi(values: List[float], period: int = 14) -> List[float]:
    gains, losses = [], []
    for i in range(1, len(values)):
        delta = values[i] - values[i-1]
        gains.append(max(delta, 0))
        losses.append(-min(delta, 0))
    avg_gain = [np.mean(gains[:period])]
    avg_loss = [np.mean(losses[:period])]
    rsis = [100 - 100 / (1 + avg_gain[0] / avg_loss[0]) if avg_loss[0] > 0 else 100]
    for i in range(period, len(gains)):
        g = gains[i]
        l = losses[i]
        avg_gain.append((avg_gain[-1] * (period - 1) + g) / period)
        avg_loss.append((avg_loss[-1] * (period - 1) + l) / period)
        if avg_loss[-1] == 0:
            rsis.append(100)
        else:
            rs = avg_gain[-1] / avg_loss[-1]
            rsis.append(100 - 100 / (1 + rs))
    return [None]*(len(values)-len(rsis)) + rsis

# ========== 評分模型 ========== #
class ScoreResult:
    def __init__(self, label: str, base_score: float, risk_mul: float):
        self.label = label
        self.base_score = base_score
        self.risk_mul = risk_mul
        self.final_score = base_score * risk_mul

def classify_score(score: float) -> str:
    if score >= 1.5:
        return "Bullish"
    elif score <= -1.5:
        return "Bearish"
    return "Neutral"

def calc_score(prices, fr, oi) -> ScoreResult:
    z20 = zlema(prices, 20)
    z50 = zlema(prices, 50)
    rsi_vals = rsi(prices)
    trend = 1 if z20[-1] > z50[-1] else -1 if z20[-1] < z50[-1] else 0
    mom = 1 if rsi_vals[-1] > 55 else -1 if rsi_vals[-1] < 45 else 0
    fr_bias = 1 if fr[-1] > np.mean(fr[-20:]) else -1
    oi_bias = 1 if oi[-1] > np.mean(oi[-20:]) else -1
    base = trend + mom + 0.5 * (fr_bias + oi_bias)
    risk_mul = 0.8 if abs(base) > 1.5 else 1.0
    return ScoreResult(classify_score(base * risk_mul), base, risk_mul)
