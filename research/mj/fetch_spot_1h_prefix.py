"""Fetch Binance SPOT 1h klines (public REST, no key) from 2017-08 up to the first USD-M 1h bar, per major.

Output: data/raw/spot_majors_20260925/{SYM}_spot_1h_2017.parquet (+ manifest_1h.json). Used only as a training-history
prefix for 1h-derived features, mirroring the audited 4h/1d spot prefix of v92.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pandas as pd
import requests

OUT = Path("data/raw/spot_majors_20260925")
PERP_1H = {"BTCUSDT": Path("data/raw/ma_ribbon_20260924/klines_1h.parquet")}
PERP_1H.update({s: Path(f"data/raw/majors_intraday_20260924/{s}_1h.parquet") for s in ("ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT")})
COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "num_trades", "taker_buy_volume", "taker_buy_quote_volume", "ignore"]


def fetch(sym: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    s = requests.Session()
    rows, t = [], int(start.timestamp() * 1000)
    while t < int(end.timestamp() * 1000):
        r = s.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "1h", "startTime": t, "limit": 1000}, timeout=60)
        r.raise_for_status()
        k = r.json()
        if not k:
            break
        rows += k
        t = k[-1][0] + 3600_000
        time.sleep(0.2)
    d = pd.DataFrame(rows, columns=COLS).drop(columns="ignore")
    for c in COLS[1:6] + COLS[7:11]:
        if c in d:
            d[c] = d[c].astype(float)
    d["open_time"] = pd.to_datetime(d["open_time"], unit="ms", utc=True)
    d["close_time"] = pd.to_datetime(d["close_time"], unit="ms", utc=True)
    return d[d["open_time"] < end].drop_duplicates("open_time").reset_index(drop=True)


def main():
    man = {"source": "Binance SPOT public REST 1h (api.binance.com/api/v3/klines)", "files": {}}
    for sym, p in PERP_1H.items():
        first_perp = pd.to_datetime(pd.read_parquet(p, columns=["open_time"])["open_time"], utc=True).min()
        d = fetch(sym, pd.Timestamp("2017-08-01", tz="UTC"), first_perp)
        f = OUT / f"{sym}_spot_1h_2017.parquet"
        d.to_parquet(f, index=False)
        man["files"][sym] = dict(rows=len(d), first=str(d.open_time.min()) if len(d) else None, last=str(d.open_time.max()) if len(d) else None,
                                 perp_1h_first=str(first_perp), sha256=hashlib.sha256(f.read_bytes()).hexdigest())
        print(sym, man["files"][sym], flush=True)
    (OUT / "manifest_1h.json").write_text(json.dumps(man, indent=1))


if __name__ == "__main__":
    main()
