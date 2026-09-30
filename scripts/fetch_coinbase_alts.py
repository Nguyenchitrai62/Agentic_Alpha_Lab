"""Download Coinbase Exchange public 1h candles for SOL-USD and XRP-USD once (no keys) -> data/raw/coinbase_alts_20260930/.

Resumable: an existing file is extended from its last stored hour. Only closed candles are kept. A manifest records rows / range / sha256.
  python scripts/fetch_coinbase_alts.py
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/raw/coinbase_alts_20260930"
START = pd.Timestamp("2021-01-01", tz="UTC")


def fetch(product: str, s: requests.Session) -> pd.DataFrame:
    f = OUT / f"{product}_1h.parquet"
    old = pd.read_parquet(f) if f.exists() else pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume"])
    t = (pd.to_datetime(old["open_time"], utc=True).max() + pd.Timedelta(hours=1)) if len(old) else START
    end = pd.Timestamp.now(tz="UTC").floor("h")
    rows = []
    while t < end:
        t2 = min(t + pd.Timedelta(hours=300), end)
        for attempt in range(5):
            r = s.get(f"https://api.exchange.coinbase.com/products/{product}/candles",
                      params={"granularity": 3600, "start": t.isoformat(), "end": t2.isoformat()}, timeout=60)
            if r.status_code == 429:
                time.sleep(2 + 2 * attempt)
                continue
            r.raise_for_status()
            break
        rows += r.json()
        t = t2
        time.sleep(0.15)
    d = pd.DataFrame(rows, columns=["time", "low", "high", "open", "close", "volume"])
    d["open_time"] = pd.to_datetime(d["time"], unit="s", utc=True)
    d = d[d.open_time < end][["open_time", "open", "high", "low", "close", "volume"]]
    full = pd.concat([old, d], ignore_index=True)
    full["open_time"] = pd.to_datetime(full["open_time"], utc=True)
    full = full.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
    full.to_parquet(f, index=False)
    return full


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    man = {"source": "Coinbase Exchange public REST candles granularity 3600", "fetched_at": pd.Timestamp.now(tz="UTC").isoformat(), "files": {}}
    for p in ("SOL-USD", "XRP-USD"):
        d = fetch(p, s)
        f = OUT / f"{p}_1h.parquet"
        man["files"][p] = {"rows": int(len(d)), "first": str(d.open_time.min()), "last": str(d.open_time.max()),
                           "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}
        print(p, man["files"][p], flush=True)
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1))


if __name__ == "__main__":
    main()
