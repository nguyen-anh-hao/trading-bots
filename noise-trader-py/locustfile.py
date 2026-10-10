"""Locust noise trader — multi-strategy market simulator + load test.

Mỗi "user" Locust là một persona giao dịch có trạng thái riêng, pha trộn nhiều
chiến thuật (thông minh + cờ bạc) để priceboard nhảy loạn khi chạy:
    locust -f locustfile.py --headless -u 30 -r 4 --run-time 2m --host http://localhost:8080
"""
import random
from collections import defaultdict, deque

from locust import HttpUser, between, task

SYMBOLS = ["AAPL", "MSFT", "TSLA", "NVDA", "AMD", "GOOG"]
BASE_PRICES = {"AAPL": 150.0, "MSFT": 300.0, "TSLA": 220.0, "NVDA": 450.0, "AMD": 120.0, "GOOG": 140.0}


class NoiseTrader(HttpUser):
    wait_time = between(0.02, 0.15)

    def on_start(self):
        self.client.headers.update({"X-API-Key": "demo-key", "Content-Type": "application/json"})
        self.last_prices = dict(BASE_PRICES)
        self.history = defaultdict(lambda: deque(maxlen=30))

        # 1. Tạo account + API key riêng cho persona này (dùng admin key demo-key).
        try:
            r = self.client.post("/accounts", json={"name": "bot"})
            account_id = (r.json() or {}).get("account_id", 0)
            if account_id:
                r = self.client.post("/accounts/api-keys", json={
                    "account_id": account_id,
                    "permissions": ["read_only", "trade", "withdraw"],
                })
                api_key = (r.json() or {}).get("api_key")
                if api_key:
                    self.client.headers.update({"X-API-Key": api_key})
        except Exception:
            pass  # fallback về demo-key nếu tạo account lỗi

        # 2. Nạp vốn riêng cho account mới, rồi đặt lệnh 2 phía tạo thanh khoản.
        self.client.post("/deposit", json={"asset": "CASH", "amount": "5000000"})
        for sym in SYMBOLS:
            self.client.post("/deposit", json={"asset": f"STOCK:{sym}", "amount": "50000"})
            mid = self.last_prices[sym]
            self._limit(sym, "BUY", random.randint(5, 30), mid * 0.995)
            self._limit(sym, "SELL", random.randint(5, 30), mid * 1.005)

    def _limit(self, symbol, side, qty, price):
        self.client.post("/orders", json={
            "symbol": symbol, "side": side, "type": "LIMIT",
            "price": str(round(price, 2)), "quantity": str(qty), "time_in_force": "GTC",
        })

    def _market(self, symbol, side, qty):
        self.client.post("/orders", json={
            "symbol": symbol, "side": side, "type": "MARKET",
            "quantity": str(qty), "time_in_force": "IOC",
        })

    def _refresh(self, symbol):
        mid = self.last_prices.get(symbol, BASE_PRICES.get(symbol, 100.0))
        try:
            r = self.client.get(f"/ticker?symbol={symbol}")
            t = (r.json() or {}).get("ticker", {})
            last = float(t.get("last_price") or 0)
            bid = float(t.get("best_bid") or 0)
            ask = float(t.get("best_ask") or 0)
            if last > 0:
                mid = last
            elif bid > 0 and ask > 0:
                mid = (bid + ask) / 2
        except Exception:
            pass
        self.last_prices[symbol] = mid
        self.history[symbol].append(mid)
        return mid

    def _sma(self, symbol, n=6):
        h = list(self.history[symbol])
        if not h:
            return self.last_prices.get(symbol, 100.0)
        w = h[-n:]
        return sum(w) / len(w)

    @task(26)
    def gamble(self):
        symbol = random.choice(SYMBOLS)
        mid = self._refresh(symbol)
        side = random.choice(["BUY", "SELL"])
        qty = random.choice([1, 5, 20, 50, 150, 400])
        if random.random() < 0.55:
            self._market(symbol, side, qty)
        else:
            off = mid * random.uniform(0.001, 0.12)
            self._limit(symbol, side, qty, mid + off if side == "SELL" else mid - off)

    @task(16)
    def market_make(self):
        symbol = random.choice(SYMBOLS)
        mid = self._refresh(symbol)
        spread = mid * random.uniform(0.002, 0.015)
        self._limit(symbol, "BUY", random.randint(1, 15), mid - spread / 2)
        self._limit(symbol, "SELL", random.randint(1, 15), mid + spread / 2)

    @task(14)
    def momentum(self):
        symbol = random.choice(SYMBOLS)
        self._refresh(symbol)
        recent = list(self.history[symbol])[-3:]
        if len(recent) < 2:
            return
        side = "BUY" if recent[-1] > recent[0] else "SELL"
        mid = self.last_prices[symbol]
        price = mid * (1 + random.uniform(0.002, 0.02) * (1 if side == "SELL" else -1))
        self._limit(symbol, side, random.randint(1, 25), price)

    @task(12)
    def mean_revert(self):
        symbol = random.choice(SYMBOLS)
        mid = self._refresh(symbol)
        sma = self._sma(symbol)
        if sma <= 0:
            return
        dev = (mid - sma) / sma
        if abs(dev) < 0.003:
            return
        side = "SELL" if dev > 0 else "BUY"
        price = mid * (1 + random.uniform(0.002, 0.02) * (1 if side == "SELL" else -1))
        self._limit(symbol, side, random.randint(1, 20), price)

    @task(10)
    def fomo(self):
        symbol = random.choice(SYMBOLS)
        self._refresh(symbol)
        recent = list(self.history[symbol])[-2:]
        if len(recent) == 2 and recent[1] > recent[0] * 1.005:
            self._market(symbol, "BUY", random.randint(30, 200))

    @task(10)
    def panic(self):
        symbol = random.choice(SYMBOLS)
        self._refresh(symbol)
        recent = list(self.history[symbol])[-2:]
        if len(recent) == 2 and recent[1] < recent[0] * 0.995:
            self._market(symbol, "SELL", random.randint(30, 200))

    @task(7)
    def spoof(self):
        symbol = random.choice(SYMBOLS)
        mid = self._refresh(symbol)
        side = random.choice(["BUY", "SELL"])
        price = mid * (1 - random.uniform(0.03, 0.12)) if side == "BUY" else mid * (1 + random.uniform(0.03, 0.12))
        self._limit(symbol, side, random.randint(500, 3000), price)

    @task(4)
    def read_ticker(self):
        symbol = random.choice(SYMBOLS)
        self.client.get(f"/ticker?symbol={symbol}")

    @task(1)
    def read_book(self):
        symbol = random.choice(SYMBOLS)
        self.client.get(f"/book?symbol={symbol}&depth=5")
