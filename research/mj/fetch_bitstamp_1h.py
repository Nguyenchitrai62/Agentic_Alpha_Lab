"""Fetch Bitstamp public 1h OHLC for btcusd (no key) from 2011-09-01 to 2015-08-01.

Output: data/raw/bitstamp_20260925/btcusd_1h_2011_2015.parquet (+ manifest.json). Training-history prefix for v114.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pandas as pd
import requests

OUT = Path("data/raw/bitstamp_20260925")


def main():
    s = requests.Session()
    start, end = int(pd.Timestamp("2011-09-01", tz="UTC").timestamp()), int(pd.Timestamp("2015-08-01", tz="UTC").timestamp())
    rows, t = [], start
    while t < end:
        r = s.get("https://www.bitstamp.net/api/v2/ohlc/btcusd/", params={"step": 3600, "limit": 1000, "start": t}, timeout=60)
        r.raise_for_status()
        k = r.json()["data"]["ohlc"]
        if not k:
            t += 1000 * 3600
            continue
        rows += k
        nxt = int(k[-1]["timestamp"]) + 3600
        t = nxt if nxt > t else t + 1000 * 3600
        time.sleep(0.3)
    d = pd.DataFrame(rows)
    for c in ("open", "high", "low", "close", "volume"):
        d[c] = d[c].astype(float)
    d["open_time"] = pd.to_datetime(d["timestamp"].astype(int), unit="s", utc=True)
    d = d.drop(columns="timestamp").drop_duplicates("open_time").sort_values("open_time")
    d = d[d.open_time < pd.Timestamp("2015-08-01", tz="UTC")][["open_time", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / "btcusd_1h_2011_2015.parquet"
    d.to_parquet(f, index=False)
    man = dict(source="Bitstamp public REST /api/v2/ohlc/btcusd step 3600", rows=len(d), first=str(d.open_time.min()), last=str(d.open_time.max()),
               zero_volume_rows=int((d.volume == 0).sum()), sha256=hashlib.sha256(f.read_bytes()).hexdigest())
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1))
    print(man)


if __name__ == "__main__":
    main()
