"""Train/serve-skew audit, Coinbase member inputs: the stored Coinbase 1h candles and Binance spot 4h klines that feed v111.add_cb
(data/raw/coinbase_20260925, data/raw/spot_majors_20260925; rows after ~2026-09-24 were appended live by scripts/coinbase_spot_update.py
right after each close) vs a fresh re-download now (public endpoints, read-only), for 2026-09-01 .. the last closed bar.
Also the resulting premium features (v111.premium on stored vs re-downloaded inputs). Output: parity/cb_refetch_parity.json.
"""

from __future__ import annotations

import importlib.util
import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
os.chdir(ROOT)
START = pd.Timestamp("2026-09-01", tz="UTC")
S = requests.Session()
S.headers["User-Agent"] = "agentic-alpha-lab-research"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def cb_fetch(product, start, end):
    rows, t = [], start
    while t < end:
        t2 = min(t + pd.Timedelta(hours=300), end)
        r = S.get(f"https://api.exchange.coinbase.com/products/{product}/candles",
                  params={"granularity": 3600, "start": t.isoformat(), "end": t2.isoformat()}, timeout=60)
        r.raise_for_status()
        rows += r.json()
        t = t2
        time.sleep(0.5)
    d = pd.DataFrame(rows, columns=["time", "low", "high", "open", "close", "volume"])
    d["open_time"] = pd.to_datetime(d["time"], unit="s", utc=True)
    return d.drop_duplicates("open_time").set_index("open_time").sort_index()


def spot_fetch(sym, start, end):
    r = S.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "4h", "startTime": int(start.value // 1e6),
                                                                 "endTime": int(end.value // 1e6) - 1, "limit": 1000}, timeout=60)
    r.raise_for_status()
    d = pd.DataFrame(r.json()).iloc[:, :7]
    d.columns = ["open_time", "open", "high", "low", "close", "volume", "close_time"]
    d["open_time"] = pd.to_datetime(d["open_time"], unit="ms", utc=True)
    return d.set_index("open_time").astype(float)


def main():
    now = pd.Timestamp.now(tz="UTC")
    end_h, end_4h = now.floor("h"), now.floor("4h")
    out = {"window": [str(START), str(end_h)], "coinbase_1h": {}, "binance_spot_4h": {}, "premium_features": {}}
    fresh_cb, fresh_sp = {}, {}
    for p in ("BTC-USD", "ETH-USD"):
        st = pd.read_parquet(f"data/raw/coinbase_20260925/{p}_1h.parquet")
        st["open_time"] = pd.to_datetime(st["open_time"], utc=True)
        st = st.drop_duplicates("open_time").set_index("open_time").sort_index()
        fr = cb_fetch(p, START, end_h)
        fresh_cb[p] = fr
        j = st.join(fr[["open", "high", "low", "close", "volume"]], rsuffix="_new", how="inner")
        j = j[(j.index >= START) & (j.index < end_h)]
        d = {c: {"max_rel": float((j[c].astype(float) / j[c + "_new"].astype(float) - 1).abs().max()),
                 "n_rel_gt_1e-9": int(((j[c].astype(float) / j[c + "_new"].astype(float) - 1).abs() > 1e-9).sum())}
             for c in ("open", "high", "low", "close", "volume")}
        live_part = j[j.index >= pd.Timestamp("2026-09-25", tz="UTC")]
        d["close_max_rel_after_2026-09-25"] = float((live_part["close"].astype(float) / live_part["close_new"] - 1).abs().max())
        d["volume_max_rel_after_2026-09-25"] = float((live_part["volume"].astype(float) / live_part["volume_new"] - 1).abs().max())
        d["rows_compared"], d["stored_missing"], d["fresh_missing"] = len(j), int(len(fr[(fr.index >= START) & (fr.index < end_h)].index.difference(st.index))), \
            int(len(st[(st.index >= START) & (st.index < end_h)].index.difference(fr.index)))
        out["coinbase_1h"][p] = d
    for sym in ("BTCUSDT", "ETHUSDT"):
        st = pd.read_parquet(f"data/raw/spot_majors_20260925/{sym}_spot_4h.parquet")
        st["open_time"] = pd.to_datetime(st["open_time"], utc=True)
        st = st.drop_duplicates("open_time").set_index("open_time").sort_index()
        fr = spot_fetch(sym, START, end_4h)
        fresh_sp[sym] = fr
        j = st[["close", "volume"]].astype(float).join(fr[["close", "volume"]], rsuffix="_new", how="inner")
        out["binance_spot_4h"][sym] = {"rows": len(j), "close_max_rel": float((j.close / j.close_new - 1).abs().max()),
                                       "volume_max_rel": float((j.volume / j.volume_new - 1).abs().max())}
    # premium features on stored vs fresh inputs (same v111 code; fresh inputs patched in for the window)
    v111 = _load("par_v111_cb", ROOT / "research/parallel/rounds/parallel-20260906-r2/v111/v111_coinbase_premium.py")
    times = pd.DataFrame({"t": pd.date_range(START, end_4h - pd.Timedelta(hours=4), freq="4h", tz="UTC"), "sym": "X"})
    stored = v111.add_cb(times).set_index("t")
    orig_rp = pd.read_parquet

    def patched(path, *a, **k):
        d = orig_rp(path, *a, **k)
        p = str(path).replace("\\", "/")
        for prod, fr in fresh_cb.items():
            if p.endswith(f"coinbase_20260925/{prod}_1h.parquet"):
                d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
                new = fr.reset_index()[["open_time", "open", "high", "low", "close", "volume"]]
                d = pd.concat([d[d.open_time < START], new], ignore_index=True)
        for sym, fr in fresh_sp.items():
            if p.endswith(f"spot_majors_20260925/{sym}_spot_4h.parquet"):
                d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
                new = fr.reset_index()[["open_time", "close"]]
                d = pd.concat([d[d.open_time < START], new], ignore_index=True)
        return d
    v111.pd.read_parquet = patched
    try:
        fresh = v111.add_cb(times).set_index("t")
    finally:
        v111.pd.read_parquet = orig_rp
    for c in v111.CB:
        a, b = stored[c].astype(float), fresh[c].astype(float)
        ok = a.notna() & b.notna()
        out["premium_features"][c] = {"max_abs_diff": float((a[ok] - b[ok]).abs().max()), "frac_eq_1e-6": round(float(((a - b).abs() <= 1e-6)[ok].mean()), 4),
                                      "nan_mismatch": int((a.isna() ^ b.isna()).sum()), "std": float(a[ok].std())}
    (HERE / "cb_refetch_parity.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
