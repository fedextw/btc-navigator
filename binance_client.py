"""Rate-budgeted Binance access. 429/418 pause the worker rather than retrying in a loop."""
import threading
import time
import requests
from market_data import FUTURES


class RatePause(RuntimeError):
    pass


class BinanceAccessError(RuntimeError):
    pass


class RequestBudget:
    def __init__(self, limit=1200, clock=time.monotonic, gap=.08):
        self.limit, self.clock, self.gap = limit, clock, gap
        self.window, self.used, self.blocked_until, self.last_request = clock(), 0, 0.0, -1.0
        self.lock = threading.Lock()

    def acquire(self, weight):
        with self.lock:
            now = self.clock()
            if now - self.window >= 60:
                self.window, self.used = now, 0
            if now < self.blocked_until or self.used + weight > self.limit:
                raise RatePause("等待交易所速率額度恢復")
            delay = max(0, self.gap - (now - self.last_request))
            if delay:
                time.sleep(delay)
            self.last_request = self.clock()
            self.used += weight

    def pause(self, seconds):
        with self.lock:
            self.blocked_until = max(self.blocked_until, self.clock() + seconds)


class BinanceClient:
    def __init__(self, budget=None, get=requests.get):
        self.budget = budget or RequestBudget()
        self.get = get

    def json(self, path, params=None, weight=1):
        self.budget.acquire(weight)
        response = self.get(FUTURES + path, params=params, timeout=(3, 8))
        if response.status_code in (418, 429):
            try:
                seconds = max(1, min(float(response.headers.get("Retry-After", "300" if response.status_code == 418 else "60")), 3600))
            except (ValueError, TypeError):
                seconds = 60
            self.budget.pause(seconds)
            raise RatePause("交易所要求暫停請求")
        if response.status_code == 451:
            raise BinanceAccessError("Binance 對目前所在地區限制服務（HTTP 451）；請檢查合法可用的服務地區")
        if response.status_code >= 400:
            raise BinanceAccessError(f"Binance 公開 API 拒絕請求（HTTP {response.status_code}）")
        return response.json()
