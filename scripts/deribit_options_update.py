"""Incrementally append closed 4h Deribit BTC option-trade aggregates to data/raw/deribit_opt_20260926/BTC_options_4h.parquet.

Uses the same public endpoint and aggregation as research/mj/fetch_deribit_options_4h.py; only bars after the last
stored bar and fully closed (end <= now) are fetched. Safe to run every 4h (idempotent).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "data/raw/deribit_opt_20260926/BTC_options_4h.parquet"
spec = importlib.util.spec_from_file_location("fetch_deribit", ROOT / "research/mj/fetch_deribit_options_4h.py")
fd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fd)


def update(cur: str = "BTC") -> int:
    old = pd.read_parquet(FILE)
    old["bar"] = pd.to_datetime(old["bar"], utc=True)
    last = old["bar"].max()
    now = pd.Timestamp.now(tz="UTC")
    s = requests.Session()
    new = []
    for w0 in pd.date_range(last + pd.Timedelta(hours=4), now.floor("4h") - pd.Timedelta(hours=4), freq="4h"):
        tr = fd.fetch_window(s, cur, int(w0.timestamp() * 1000), int((w0 + pd.Timedelta(hours=4)).timestamp() * 1000) - 1)
        a = fd.aggregate(tr)
        if len(a):
            new.append(a.reset_index(names="bar"))
    if new:
        full = pd.concat([old] + new, ignore_index=True)
        full["bar"] = pd.to_datetime(full["bar"], utc=True)
        full = full.drop_duplicates("bar", keep="last").sort_values("bar").reset_index(drop=True)
        full.to_parquet(FILE, index=False)
    return sum(len(x) for x in new)


if __name__ == "__main__":
    print("appended bars:", update())
