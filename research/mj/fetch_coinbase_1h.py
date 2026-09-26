"""Fetch Coinbase Exchange public 1h candles (no key) for BTC-USD and ETH-USD from 2017-08-01.

Output: data/raw/coinbase_20260925/{PRODUCT}_1h.parquet with open_time (UTC, candle start), open/high/low/close/volume
(+ manifest.json). Used for the Coinbase-vs-Binance premium features (v111).
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pandas as pd
import requests

OUT = Path("data/raw/coinbase_20260925")
URL = "https://api.exchange.coinbase.com/products/{p}/candles"


def fetch(product: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    s = requests.Session()
    s.headers["User-Agent"] = "agentic-alpha-lab-research"
    rows, t = [], start
    while t < end:
        t2 = min(t + pd.Timedelta(hours=300), end)
        for attempt in range(5):
            r = s.get(URL.format(p=product), params={"granularity": 3600, "start": t.isoformat(), "end": t2.isoformat()}, timeout=60)
            if r.status_code == 429:
                time.sleep(2 + attempt * 2)
                continue
            r.raise_for_status()
            break
        rows += r.json()
        t = t2
        time.sleep(0.15)
    d = pd.DataFrame(rows, columns=["time", "low", "high", "open", "close", "volume"])
    d["open_time"] = pd.to_datetime(d["time"], unit="s", utc=True)
    d = d.drop(columns="time").drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
    return d[["open_time", "open", "high", "low", "close", "volume"]]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    end = pd.Timestamp.now(tz="UTC").floor("h")
    man = {"source": "Coinbase Exchange public REST candles granularity 3600", "fetched_until": str(end), "files": {}}
    for p in ("BTC-USD", "ETH-USD"):
        d = fetch(p, pd.Timestamp("2017-08-01", tz="UTC"), end)
        f = OUT / f"{p}_1h.parquet"
        d.to_parquet(f, index=False)
        man["files"][p] = dict(rows=len(d), first=str(d.open_time.min()), last=str(d.open_time.max()), sha256=hashlib.sha256(f.read_bytes()).hexdigest())
        print(p, man["files"][p], flush=True)
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1))


if __name__ == "__main__":
    main()
