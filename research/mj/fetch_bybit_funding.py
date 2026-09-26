"""Fetch Bybit public linear-perp funding history (no key) for the 5 majors.

Output: data/raw/bybit_20260925/{SYM}_funding.parquet (fundingTime UTC, fundingRate) + manifest.json.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pandas as pd
import requests

OUT = Path("data/raw/bybit_20260925")
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")


def fetch(sym: str) -> pd.DataFrame:
    s = requests.Session()
    rows, end = [], int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)
    while True:
        r = s.get("https://api.bybit.com/v5/market/funding/history", params={"category": "linear", "symbol": sym, "limit": 200, "endTime": end}, timeout=60)
        r.raise_for_status()
        k = r.json()["result"]["list"]
        if not k:
            break
        rows += k
        oldest = min(int(x["fundingRateTimestamp"]) for x in k)
        if oldest >= end:
            break
        end = oldest - 1
        time.sleep(0.15)
    d = pd.DataFrame(rows)
    d["fundingTime"] = pd.to_datetime(d["fundingRateTimestamp"].astype("int64"), unit="ms", utc=True)
    d["fundingRate"] = d["fundingRate"].astype(float)
    return d[["fundingTime", "fundingRate"]].drop_duplicates("fundingTime").sort_values("fundingTime").reset_index(drop=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    man = {"source": "Bybit public REST /v5/market/funding/history category=linear", "files": {}}
    for sym in SYMS:
        d = fetch(sym)
        f = OUT / f"{sym}_funding.parquet"
        d.to_parquet(f, index=False)
        man["files"][sym] = dict(rows=len(d), first=str(d.fundingTime.min()), last=str(d.fundingTime.max()), sha256=hashlib.sha256(f.read_bytes()).hexdigest())
        print(sym, man["files"][sym], flush=True)
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1))


if __name__ == "__main__":
    main()
