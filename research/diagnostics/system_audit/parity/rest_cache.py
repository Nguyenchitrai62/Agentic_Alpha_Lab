"""Parity audit helper: fetch public Binance USD-M 4h / 1d klines and funding once and cache them under parity/cache (read-only audit,
no orders, no writes outside this directory). Rate-limit aware: pauses when the IP's used weight passes 1000/min."""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
BASE = "https://fapi.binance.com"
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
KCOLS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "num_trades",
         "taker_buy_volume", "taker_buy_quote_volume", "ignore"]
S = requests.Session()


def get(url, params):
    for _ in range(5):
        r = S.get(url, params=params, timeout=60)
        if r.status_code in (418, 429):
            time.sleep(65)
            continue
        r.raise_for_status()
        if int(r.headers.get("X-MBX-USED-WEIGHT-1M", 0) or 0) > 1000:
            time.sleep(61 - time.time() % 60)
        return r.json()
    raise RuntimeError("rate limited")


def klines(sym, interval, start, end):
    step = {"1m": 60_000, "4h": 4 * 3600_000, "1d": 86400_000}[interval]
    cur, stop, rows = int(pd.Timestamp(start).value // 1e6), int(pd.Timestamp(end).value // 1e6), []
    while cur < stop:
        b = get(f"{BASE}/fapi/v1/klines", {"symbol": sym, "interval": interval, "startTime": cur, "endTime": stop, "limit": 1500})
        if not b:
            break
        rows += b
        cur = int(b[-1][0]) + step
        if len(b) < 1500:
            break
    d = pd.DataFrame(rows, columns=KCOLS).drop(columns="ignore")
    d["open_time"] = pd.to_datetime(d["open_time"], unit="ms", utc=True)
    d["close_time"] = pd.to_datetime(d["close_time"], unit="ms", utc=True)
    for c in KCOLS[1:-1]:
        if c not in ("open_time", "close_time"):
            d[c] = pd.to_numeric(d[c])
    return d.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)


def funding(sym, start, end):
    cur, stop, rows = int(pd.Timestamp(start).value // 1e6), int(pd.Timestamp(end).value // 1e6), []
    while cur < stop:
        b = get(f"{BASE}/fapi/v1/fundingRate", {"symbol": sym, "startTime": cur, "endTime": stop, "limit": 1000})
        if not b:
            break
        rows += b
        cur = int(b[-1]["fundingTime"]) + 1
        if len(b) < 1000:
            break
    f = pd.DataFrame(rows)[["fundingTime", "fundingRate"]]
    f["fundingRate"] = f["fundingRate"].astype(float)
    f["fundingTime"] = pd.to_datetime(f["fundingTime"], unit="ms", utc=True)
    return f.drop_duplicates("fundingTime").sort_values("fundingTime").reset_index(drop=True)


def cached(name, fn):
    p = CACHE / f"{name}.parquet"
    if p.exists():
        return pd.read_parquet(p)
    CACHE.mkdir(parents=True, exist_ok=True)
    d = fn()
    d.to_parquet(p)
    return d


def market_data(end):
    """4h klines from 2024-12-01, 1d from 2024-04-01, funding from 2025-06-01, all up to `end` (closed bars only)."""
    tag = pd.Timestamp(end).strftime("%Y%m%d%H")
    k4, k1d, fr = {}, {}, {}
    for s in SYMS:
        k4[s] = cached(f"k4_{s}_{tag}", lambda: klines(s, "4h", "2024-12-01", end))
        k1d[s] = cached(f"k1d_{s}_{tag}", lambda: klines(s, "1d", "2024-04-01", end))
        fr[s] = cached(f"fund_{s}_{tag}", lambda: funding(s, "2025-06-01", end))
        k4[s] = k4[s][k4[s].close_time < pd.Timestamp(end)].reset_index(drop=True)
        k1d[s] = k1d[s][k1d[s].close_time < pd.Timestamp(end)].reset_index(drop=True)
    return k4, k1d, fr
