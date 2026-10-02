"""Incrementally append closed candles used by the Coinbase-premium features (v111/v154), idempotent.

- data/raw/coinbase_20260925/{BTC,ETH}-USD_1h.parquet: Coinbase Exchange public 1h candles after the last stored hour.
- data/raw/spot_majors_20260925/{BTC,ETH}USDT_spot_4h.parquet: Binance SPOT public 4h klines after the last stored bar.
Only fully closed candles are appended. Public endpoints, no keys.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests
from agentic_alpha_lab.data.coverage import missing_ranges, require_closed_coverage

ROOT = Path(__file__).resolve().parents[1]
CB = ROOT / "data/raw/coinbase_20260925"
SP = ROOT / "data/raw/spot_majors_20260925"
# Frozen paper members need 120 days of recent rows and 540 x 4h premium warmup bars.
CHECK_START = pd.Timestamp("2026-03-01", tz="UTC")


def update_coinbase(product: str, s: requests.Session) -> int:
    f = CB / f"{product}_1h.parquet"
    old = pd.read_parquet(f)
    old["open_time"] = pd.to_datetime(old["open_time"], utc=True)
    end = pd.Timestamp.now(tz="UTC").floor("h")  # candles starting before this hour are closed
    start = CHECK_START
    step = 3600_000
    gaps = missing_ranges((t.value // 1_000_000 for t in old["open_time"]),
                          start.value // 1_000_000, end.value // 1_000_000 - step, step)
    if not gaps:
        return 0
    rows = []
    for a, b in gaps:
        t = pd.Timestamp(a, unit="ms", tz="UTC")
        stop = pd.Timestamp(b + step, unit="ms", tz="UTC")
        while t < stop:
            t2 = min(t + pd.Timedelta(hours=300), stop)
            r = s.get(f"https://api.exchange.coinbase.com/products/{product}/candles",
                      params={"granularity": 3600, "start": t.isoformat(), "end": t2.isoformat()}, timeout=60)
            r.raise_for_status()
            rows += r.json()
            t = t2
    d = pd.DataFrame(rows, columns=["time", "low", "high", "open", "close", "volume"])
    d["open_time"] = pd.to_datetime(d["time"], unit="s", utc=True)
    d = d[(d.open_time >= start) & (d.open_time < end)][["open_time", "open", "high", "low", "close", "volume"]]
    full = pd.concat([old, d], ignore_index=True).drop_duplicates("open_time", keep="first").sort_values("open_time") if len(d) else old
    full.to_parquet(f, index=False)
    require_closed_coverage(full, start, end, "1h")
    return len(d)


def update_spot(sym: str, s: requests.Session) -> int:
    f = SP / f"{sym}_spot_4h.parquet"
    old = pd.read_parquet(f)
    old["open_time"] = pd.to_datetime(old["open_time"], utc=True)
    start = CHECK_START
    now = pd.Timestamp.now(tz="UTC")
    end = now.floor("4h")
    step = 4 * 3600_000
    gaps = missing_ranges((t.value // 1_000_000 for t in old["open_time"]),
                          start.value // 1_000_000, end.value // 1_000_000 - step, step)
    if not gaps:
        return 0
    k = []
    for a, b in gaps:
        cursor = a
        while cursor <= b:
            r = s.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "4h", "startTime": cursor,
                      "endTime": b + step - 1, "limit": 1000}, timeout=60)
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            next_cursor = int(batch[-1][0]) + step
            if next_cursor <= cursor:
                raise RuntimeError("Spot candle pagination did not advance")
            k.extend(batch)
            cursor = next_cursor
    cols = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "num_trades", "taker_buy_volume", "taker_buy_quote_volume", "ignore"]
    d = pd.DataFrame(k, columns=cols).drop(columns="ignore")
    d["open_time"] = pd.to_datetime(d["open_time"], unit="ms", utc=True)
    d["close_time"] = pd.to_datetime(d["close_time"], unit="ms", utc=True)
    d = d[d["close_time"] < now]
    for c in ("open", "high", "low", "close", "volume", "quote_volume", "taker_buy_volume", "taker_buy_quote_volume"):
        d[c] = d[c].astype(float)
    d["num_trades"] = d["num_trades"].astype(old["num_trades"].dtype) if "num_trades" in old else d["num_trades"]
    d = d[old.columns.intersection(d.columns)]
    for c in d.columns:  # keep the stored dtypes (some raw files keep taker columns as strings)
        if old[c].dtype == object:
            d[c] = d[c].astype(str)
    full = pd.concat([old, d], ignore_index=True).drop_duplicates("open_time", keep="first").sort_values("open_time")
    full.to_parquet(f, index=False)
    require_closed_coverage(full, start, end, "4h")
    return len(d)


def update() -> dict:
    s = requests.Session()
    s.headers["User-Agent"] = "agentic-alpha-lab-research"
    return {"coinbase": {p: update_coinbase(p, s) for p in ("BTC-USD", "ETH-USD")},
            "spot": {x: update_spot(x, s) for x in ("BTCUSDT", "ETHUSDT")}}


if __name__ == "__main__":
    print(update())
