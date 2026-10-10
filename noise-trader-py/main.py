"""Noise trader v2 — multi-strategy market simulator.

Pha trộn nhiều "tính cách" giao dịch để tạo ra hành vi giá hỗn loạn nhưng
thực tế trên priceboard:
  - Thông minh: market making, momentum, mean reversion.
  - Ngu người / cờ bạc: FOMO, panic dump, whale order ngẫu nhiên, spoof (đặt lệnh
    ảo rồi huỷ).
Mỗi bot có thể chạy nhiều "persona" song song (NUM_BOTS) để giá nhảy dữ dội hơn.
"""
import os
import random
import threading
import time
from collections import defaultdict, deque

import requests

BASE = os.environ.get("GATEWAY_URL", "http://localhost:8080")
API_KEY = os.environ.get("API_KEY", "demo-key")
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}


def create_account():
    """Tạo tài khoản mới (public /accounts) và trả về (account_id, api_key)."""
    try:
        r = requests.post(
            f"{BASE}/accounts",
            json={"name": "noise-bot"},
            headers={"Content-Type": "application/json"},
            timeout=2,
        )
        if r is None or not r.ok:
            return None
        data = r.json()
        return int(data.get("account_id")), str(data.get("api_key"))
    except requests.RequestException:
        return None

# Số lệnh trung bình mỗi giây cho mỗi persona (Poisson-ish).
TRADE_RATE = float(os.environ.get("TRADE_RATE", "4.0"))
# Số "persona" giao dịch chạy song song (tăng để giá loạn hơn).
NUM_BOTS = int(os.environ.get("NUM_BOTS", "1"))

SYMBOLS = ["AAPL", "MSFT", "TSLA", "NVDA", "AMD", "GOOG"]

# Giá tham chiếu khởi tạo (demo không có feed thật, bot tự gieo một mức mid).
BASE_PRICES = {
    "AAPL": 150.0,
    "MSFT": 300.0,
    "TSLA": 220.0,
    "NVDA": 450.0,
    "AMD": 120.0,
    "GOOG": 140.0,
}


class Trader:
    """Một persona giao dịch với trạng thái riêng (giá, lệnh đang mở)."""

    def __init__(self, seed_offset: float = 0.0, headers: dict | None = None):
        self.headers = headers or HEADERS
        self.last_prices = {
            sym: px * (1 + seed_offset) for sym, px in BASE_PRICES.items()
        }
        self.history = defaultdict(lambda: deque(maxlen=30))
        self.open_orders = defaultdict(list)  # symbol -> [order_id]
        self.spoofs = {}  # (symbol, order_id) -> expire_time
        for sym, px in self.last_prices.items():
            self.history[sym].append(px)

    # ---------- plumbing ----------
    def _get(self, path: str):
        try:
            return requests.get(f"{BASE}{path}", headers=self.headers, timeout=2)
        except requests.RequestException:
            return None

    def _post(self, path: str, body: dict):
        try:
            return requests.post(f"{BASE}{path}", json=body, headers=self.headers, timeout=2)
        except requests.RequestException:
            return None

    def _delete(self, path: str):
        try:
            requests.delete(f"{BASE}{path}", headers=self.headers, timeout=2)
        except requests.RequestException:
            pass

    def ticker(self, symbol: str):
        r = self._get(f"/ticker?symbol={symbol}")
        if r is None or not r.ok:
            return 0.0, 0.0, 0.0
        t = r.json().get("ticker", {})
        return (
            float(t.get("last_price") or 0),
            float(t.get("best_bid") or 0),
            float(t.get("best_ask") or 0),
        )

    def refresh(self, symbol: str) -> float:
        last, bid, ask = self.ticker(symbol)
        if last > 0:
            mid = last
        elif bid > 0 and ask > 0:
            mid = (bid + ask) / 2
        else:
            mid = self.last_prices.get(symbol, BASE_PRICES.get(symbol, 100.0))
        self.last_prices[symbol] = mid
        self.history[symbol].append(mid)
        return mid

    def deposit(self, asset: str, amount: float):
        self._post("/deposit", {"asset": asset, "amount": str(amount)})

    def seed(self):
        """Nạp cổ phiếu ảo cho mọi mã + thêm tiền, rồi đặt vài lệnh tạo thanh khoản."""
        self.deposit("CASH", 5_000_000)
        for sym in SYMBOLS:
            self.deposit(f"STOCK:{sym}", 50_000)
        # Tạo sẵn sổ lệnh 2 phía để market order có thể khớp.
        for sym in SYMBOLS:
            mid = self.refresh(sym)
            for _ in range(3):
                self._place_limit(sym, "BUY", random.randint(1, 20), mid * 0.995)
                self._place_limit(sym, "SELL", random.randint(1, 20), mid * 1.005)

    def place(self, symbol: str, side: str, qty: float, price=None, type_="LIMIT", tif="GTC"):
        body = {"symbol": symbol, "side": side, "type": type_, "quantity": str(qty)}
        if type_ == "LIMIT":
            body["price"] = str(round(max(price, 0.01), 2))
        body["time_in_force"] = tif
        r = self._post("/orders", body)
        if r is not None and r.ok:
            oid = r.json().get("order_id")
            if oid:
                self.open_orders[symbol].append(oid)
                return oid
        return None

    def _place_limit(self, symbol, side, qty, price, tif="GTC"):
        return self.place(symbol, side, qty, price=price, type_="LIMIT", tif=tif)

    def cancel(self, symbol: str, oid):
        self._delete(f"/orders?id={oid}&symbol={symbol}")
        if oid in self.open_orders[symbol]:
            self.open_orders[symbol].remove(oid)
        self.spoofs.pop((symbol, oid), None)

    def bulk_cancel(self, symbol: str):
        self._post("/orders/bulk-cancel", {"symbol": symbol})
        self.open_orders[symbol].clear()

    def mid(self, symbol: str) -> float:
        return self.last_prices.get(symbol, BASE_PRICES.get(symbol, 100.0))

    def sma(self, symbol: str, n: int = 6) -> float:
        h = list(self.history[symbol])
        if not h:
            return self.mid(symbol)
        window = h[-n:]
        return sum(window) / len(window)

    def _recent(self, symbol: str, k: int = 2):
        h = list(self.history[symbol])
        return h[-k:] if len(h) >= k else []

    # ---------- strategies ----------
    def strat_gamble(self, symbol):
        """Cờ bạc: lệnh ngẫu nhiên, có thể là whale order lớn hoặc lệnh nhỏ."""
        side = random.choice(["BUY", "SELL"])
        mid = self.mid(symbol)
        if random.random() < 0.55:
            # MARKET order — đánh trực tiếp, làm giá nhảy.
            qty = random.choice([1, 5, 20, 50, 150, 400])
            self.place(symbol, side, qty, type_="MARKET", tif="IOC")
        else:
            # LIMIT order lệch khỏi mid một khoảng ngẫu nhiên.
            qty = random.choice([1, 5, 20, 50, 150, 400])
            offset = mid * random.uniform(0.001, 0.12)
            price = mid + offset if side == "SELL" else mid - offset
            self._place_limit(symbol, side, qty, price, tif=random.choice(["GTC", "IOC"]))

    def strat_momentum(self, symbol):
        """Đu trend: giá đang lên thì mua, đang xuống thì bán."""
        recent = self._recent(symbol, 3)
        if len(recent) < 2:
            return
        side = "BUY" if recent[-1] > recent[0] else "SELL"
        mid = self.mid(symbol)
        price = mid * (1 + random.uniform(0.002, 0.02) * (1 if side == "SELL" else -1))
        self._place_limit(symbol, side, random.randint(1, 25), price)

    def strat_mean_revert(self, symbol):
        """Mean reversion: lệch khỏi SMA thì đặt ngược chiều."""
        mid = self.mid(symbol)
        sma = self.sma(symbol)
        if sma <= 0:
            return
        dev = (mid - sma) / sma
        if abs(dev) < 0.003:
            return
        side = "SELL" if dev > 0 else "BUY"
        price = mid * (1 + random.uniform(0.002, 0.02) * (1 if side == "SELL" else -1))
        self._place_limit(symbol, side, random.randint(1, 20), price)

    def strat_market_make(self, symbol):
        """Market maker: quote 2 phía quanh mid."""
        mid = self.mid(symbol)
        spread = mid * random.uniform(0.002, 0.015)
        self._place_limit(symbol, "BUY", random.randint(1, 15), mid - spread / 2)
        self._place_limit(symbol, "SELL", random.randint(1, 15), mid + spread / 2)

    def strat_fomo(self, symbol):
        """FOMO: giá vọt lên thì đu mua mạnh (ngu người)."""
        recent = self._recent(symbol, 2)
        if len(recent) == 2 and recent[1] > recent[0] * 1.005:
            self.place(symbol, "BUY", random.randint(30, 200), type_="MARKET", tif="IOC")

    def strat_panic(self, symbol):
        """Panic: giá sập thì xả hàng (ngu người)."""
        recent = self._recent(symbol, 2)
        if len(recent) == 2 and recent[1] < recent[0] * 0.995:
            self.place(symbol, "SELL", random.randint(30, 200), type_="MARKET", tif="IOC")

    def strat_spoof(self, symbol):
        """Spoof: đặt lệnh lớn xa thị trường rồi huỷ sau ~1s (đánh lừa)."""
        mid = self.mid(symbol)
        side = random.choice(["BUY", "SELL"])
        price = mid * (1 - random.uniform(0.03, 0.12)) if side == "BUY" else mid * (1 + random.uniform(0.03, 0.12))
        oid = self._place_limit(symbol, side, random.randint(500, 3000), price)
        if oid:
            self.spoofs[(symbol, oid)] = time.time() + random.uniform(0.8, 2.0)

    def strat_bulk_cancel(self, symbol):
        """Dọn sạch lệnh đang mở của mã (hủy hàng loạt)."""
        if self.open_orders[symbol]:
            self.bulk_cancel(symbol)

    def reap_spoofs(self, symbol):
        now = time.time()
        for (sym, oid), exp in list(self.spoofs.items()):
            if sym == symbol and now >= exp:
                self.cancel(symbol, oid)


# (tên strategy, trọng số) — nặng về cờ bạc để giá nhảy loạn, vẫn giữ chiến thuật khôn.
STRATEGIES = [
    ("gamble", 26),
    ("momentum", 14),
    ("mean_revert", 12),
    ("market_make", 16),
    ("fomo", 10),
    ("panic", 10),
    ("spoof", 7),
    ("bulk_cancel", 5),
]
STRATEGY_NAMES = [n for n, _ in STRATEGIES]
STRATEGY_WEIGHTS = [w for _, w in STRATEGIES]


def weighted_strategy() -> str:
    return random.choices(STRATEGY_NAMES, weights=STRATEGY_WEIGHTS, k=1)[0]


def run_persona(idx: int):
    # Each persona trades as its own account so the engine's self-trade
    # prevention still leaves real counterparties to match against.
    headers = HEADERS
    acct = create_account()
    if acct is not None:
        _, api_key = acct
        headers = {"X-API-Key": api_key, "Content-Type": "application/json"}

    trader = Trader(seed_offset=random.uniform(-0.05, 0.05), headers=headers)
    trader.seed()
    while True:
        symbol = random.choice(SYMBOLS)
        trader.refresh(symbol)

        strategy = weighted_strategy()
        fn = getattr(trader, f"strat_{strategy}", trader.strat_gamble)
        try:
            fn(symbol)
        except Exception:
            pass

        trader.reap_spoofs(symbol)

        # Thỉnh thoảng huỷ một lệnh mở ngẫu nhiên để sổ lệnh xáo trộn.
        if random.random() < 0.2 and trader.open_orders[symbol]:
            oid = random.choice(trader.open_orders[symbol])
            trader.cancel(symbol, oid)

        time.sleep(random.expovariate(TRADE_RATE))


def main() -> None:
    print(f"[noise-trader] {NUM_BOTS} persona(s), rate={TRADE_RATE}/s, target={BASE}")
    threads = [
        threading.Thread(target=run_persona, args=(i,), daemon=True)
        for i in range(NUM_BOTS)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()

