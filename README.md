# Trading Bots & Simulation (`trading-bots`)

> **Synthetic Market Makers, Noise Traders & Locust Load Testing Suite** built with Python 3 and modern C++.

---

## 1. Primary Responsibility
This repository powers testing, liquidity simulation, and stress verification:
- **`noise-trader-py`:** Generates stochastic retail buy/sell flow based on Poisson process arrivals and geometric random walks. Includes headless Locust stress testing.
- **`quant-mm-cpp`:** High-frequency market-making bot providing symmetric Bid/Ask quotes around mid-price to ensure tight spreads and order book liquidity.

---

## 2. Boundaries
- Connects directly to `api-gateway` (`http://localhost:8080`) or directly to the Matching Engine port.

---

## 3. Quick Start

### Python Noise Trader
```bash
cd noise-trader-py
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Run continuous simulation
python main.py
```

### Locust Stress Test
```bash
locust -f noise-trader-py/locustfile.py --headless -u 50 -r 10 --run-time 5m --host http://localhost:8080
```

---

## 4. Engineering Roadmap (Simulation Realism & Throughput)

| Version | Phase | Target Metric & Simulation Goal |
| :--- | :--- | :--- |
| **v1.0.0** *(Current)* | **Baseline Generators** | Python HTTP Locust runner + simple Avellaneda-Stoikov market maker bot. |
| **v1.1.0** | **High-Throughput WebSocket Bots** | Async Python (`aiohttp` / `asyncio`) or Go bot client capable of blasting 20,000 orders/sec across 500 simulated trading accounts. |
| **v1.2.0** | **Historical L3 Order Book Replay** | Replay actual historical NASDAQ / Binance Level 3 order book pcap captures against the matching engine to benchmark latency under real flash-crash conditions. |
| **v2.0.0** | **DPDK / Packet-Blaster Harness** | C++ FPGA/DPDK raw UDP packet injector capable of line-rate testing (10 Million orders/sec) to identify microsecond jitter in the matching engine. |
