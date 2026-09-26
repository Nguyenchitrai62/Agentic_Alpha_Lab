"""Fetch Upbit public KRW 60-minute candles (no key) for BTC, ETH, XRP, SOL (BNB is not listed on Upbit KRW).

Output: data/raw/upbit_20260926/KRW-{COIN}_1h.parquet (open_time UTC = candle_date_time_utc, open/high/low/close in KRW,
volume) + manifest.json. Used for the Korean-premium features (v161).
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pandas as pd
import requests

OUT = Path("data/raw/upbit_20260926")
URL = "https://api.upbit.com/v1/candles/minutes/60"


def fetch(market: str, stop: pd.Timestamp) -> pd.DataFrame:
    s = requests.Session()
    rows, to = [], pd.Timestamp.now(tz="UTC").floor("h")
    while True:
        for attempt in range(6):
            r = s.get(URL, params={"market": market, "to": to.strftime("%Y-%m-%dT%H:%M:%SZ"), "count": 200}, timeout=30)
            if r.status_code == 429:
                time.sleep(1 + attempt)
                continue
            r.raise_for_status()
            break
        k = r.json()
        if not k:
            break
        rows += k
        oldest = pd.Timestamp(k[-1]["candle_date_time_utc"], tz="UTC")
        if oldest <= stop or len(k) < 200:
            break
        to = oldest
        time.sleep(0.12)
    d = pd.DataFrame(rows)
    d["open_time"] = pd.to_datetime(d["candle_date_time_utc"], utc=True)
    d = d.rename(columns={"opening_price": "open", "high_price": "high", "low_price": "low", "trade_price": "close", "candle_acc_trade_volume": "volume"})
    return d[["open_time", "open", "high", "low", "close", "volume"]].drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    man = {"source": URL, "files": {}}
    for m in ("KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-SOL"):
        d = fetch(m, pd.Timestamp("2017-10-01", tz="UTC"))
        f = OUT / f"{m}_1h.parquet"
        d.to_parquet(f, index=False)
        man["files"][m] = dict(rows=len(d), first=str(d.open_time.min()), last=str(d.open_time.max()), sha256=hashlib.sha256(f.read_bytes()).hexdigest())
        print(m, man["files"][m], flush=True)
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1))


if __name__ == "__main__":
    main()
