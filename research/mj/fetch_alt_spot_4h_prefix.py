"""Fetch Binance SPOT 4h klines (public REST, no key) of the U2020_all alts from 2017-08 up to their first USD-M 4h bar (training-history prefix only).

Universe = the 72 non-major USDT perps listed >= 28 days in Dec-2020 (data/raw/um_universe_20260930/volume_2020_12.csv, delisted included).
Prefix end = the first 4h bar of the perp history used by v316 / v317 (artifacts/research/engine_real/v316_alt4h/<SYM>.parquet). A spot pair that
the REST API no longer serves (delisted from spot) is recorded as missing - the prefix rows only extend TRAINING history before the first anchor
(2021-09-24), never the traded universe. Output: data/raw/alt_spot_4h_20261003/<SYM>_spot_4h.parquet + manifest.json.
  python research/mj/fetch_alt_spot_4h_prefix.py
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pandas as pd
import requests

OUT = Path("data/raw/alt_spot_4h_20261003")
PERP = Path("artifacts/research/engine_real/v316_alt4h")
COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "num_trades", "taker_buy_volume", "taker_buy_quote_volume", "ignore"]
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")


def fetch(sess, sym, start, end):
    rows, t = [], int(start.timestamp() * 1000)
    while t < int(end.timestamp() * 1000):
        r = sess.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "4h", "startTime": t, "limit": 1000}, timeout=60)
        if r.status_code == 400:
            return None
        r.raise_for_status()
        k = r.json()
        if not k:
            break
        rows += k
        t = k[-1][0] + 4 * 3600_000
        time.sleep(0.15)
    if not rows:
        return pd.DataFrame(columns=COLS[:-1])
    d = pd.DataFrame(rows, columns=COLS).drop(columns="ignore")
    for c in ("open", "high", "low", "close", "volume", "quote_volume", "taker_buy_volume", "taker_buy_quote_volume"):
        d[c] = d[c].astype(float)
    d["num_trades"] = d["num_trades"].astype(float)
    d["open_time"] = pd.to_datetime(d["open_time"], unit="ms", utc=True)
    d["close_time"] = pd.to_datetime(d["close_time"], unit="ms", utc=True)
    return d[d["open_time"] < end].drop_duplicates("open_time").reset_index(drop=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    v = pd.read_csv("data/raw/um_universe_20260930/volume_2020_12.csv")
    uni = list(v[(v.days >= 28) & ~v.symbol.isin(MAJORS)].sort_values("quote_volume_usd", ascending=False).symbol)
    man = {"source": "Binance SPOT public REST 4h (api.binance.com/api/v3/klines)", "files": {}, "missing": []}
    sess = requests.Session()
    for sym in uni:
        p = PERP / f"{sym}.parquet"
        if not p.exists():
            man["missing"].append([sym, "no perp 4h cache"])
            continue
        first_perp = pd.to_datetime(pd.read_parquet(p, columns=["open_time"])["open_time"], utc=True).min()
        d = fetch(sess, sym, pd.Timestamp("2017-08-01", tz="UTC"), first_perp)
        if d is None:
            man["missing"].append([sym, "spot pair not served"])
            print(sym, "missing", flush=True)
            continue
        f = OUT / f"{sym}_spot_4h.parquet"
        d.to_parquet(f, index=False)
        man["files"][sym] = dict(rows=len(d), first=str(d.open_time.min()) if len(d) else None, last=str(d.open_time.max()) if len(d) else None,
                                 perp_first=str(first_perp), sha256=hashlib.sha256(f.read_bytes()).hexdigest())
        print(sym, man["files"][sym]["rows"], man["files"][sym]["first"], flush=True)
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1))
    print("done", len(man["files"]), "files,", len(man["missing"]), "missing")


if __name__ == "__main__":
    main()
