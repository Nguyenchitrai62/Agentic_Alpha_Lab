"""v113: longer training history for the v96 books from Coinbase 2015-2017 (registry parallel-20260906-r2 / v113).

BTC and ETH get an extra prefix before their Binance spot 2017 prefix: Coinbase BTC-USD (from 2015-07-20) and ETH-USD
(from 2016-05-18) 1h candles (data/raw/coinbase_20260925/*_1h_pre2017.parquet + *_1h.parquet, contiguous up to the Binance start) aggregated to UTC 4h and 1d bars
(open first, high max, low min, close last, volume sum, quote_volume = sum(volume*close), close_time = bar end - 1ms;
bars with fewer than 3 of 4 hours (4h) or 20 of 24 hours (1d) dropped). Only rows before the first existing bar are
added, so test rows are unchanged; the prefix adds training rows only (funding/taker columns absent -> NaN as for the
2017 spot prefix). Books: v92 long-only, v94 long/short, and the v96 50/50 blend (own 20% vol targets), all retrained
on the extended panel; audited code paths otherwise. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v113/v113_longer_history.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, HERE.parent / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v92 = _load("v92", "v92/v92_pooled_hgb_vt.py")
v94 = _load("v94", "v94/v94_long_short_ensemble.py")  # v94 loads its own v92 copy; only its functions on our panel are used
v103 = _load("v103", "v103/v103_flow_short_horizon.py")
CB = {"BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD"}
_orig_load = v92.load_asset


def cb_bars(product: str, rule: str, min_hours: int) -> pd.DataFrame:
    h = pd.concat([pd.read_parquet(f"data/raw/coinbase_20260925/{product}_1h_pre2017.parquet"),
                   pd.read_parquet(f"data/raw/coinbase_20260925/{product}_1h.parquet")], ignore_index=True)
    h["open_time"] = pd.to_datetime(h["open_time"], utc=True)
    h = h.drop_duplicates("open_time").set_index("open_time").sort_index()
    h["qv"] = h["volume"] * h["close"]
    g = h.resample(rule, label="left", closed="left")
    b = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last(),
                      "volume": g["volume"].sum(), "quote_volume": g["qv"].sum(), "n": g["close"].count()})
    b = b[b["n"] >= min_hours].drop(columns="n").reset_index()
    b["close_time"] = b["open_time"] + pd.Timedelta(rule) - pd.Timedelta(milliseconds=1)
    return b


def load_asset_ext(s):
    b, d, f = _orig_load(s)
    if s in CB:
        pb, pdly = cb_bars(CB[s], "4h", 3), cb_bars(CB[s], "1D", 20)
        pb = pb[pb["open_time"] < b["open_time"].iloc[0]]
        pdly = pdly[pdly["open_time"] < d["open_time"].iloc[0]]
        b = pd.concat([pb, b], ignore_index=True)
        d = pd.concat([pdly, d], ignore_index=True)
    return b.sort_values("open_time").reset_index(drop=True), d.sort_values("open_time").reset_index(drop=True), f


def main():
    v92.load_asset = load_asset_ext
    panel = v92.build()
    first = {s: str(g["t"].min()) for s, g in panel.groupby("sym")}
    print("first rows", first, flush=True)
    v92.FEATS = [c for c in panel.columns if c not in ("y", "t", "open", "sym", "bar")]
    lo, ic = [], {}
    for a in v92.ANCHORS:
        te, n = v92.train_predict(panel, a)
        lo.append(te)
        ic[a] = dict(train_rows=n, ic_v92=round(float(te[["pred", "y"]].corr(method="spearman").iloc[0, 1]), 4))
    lo = pd.concat(lo, ignore_index=True)
    p94 = v94.add_targets(panel)
    f94 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    ls = []
    for a in v92.ANCHORS:
        te, _ = v94.train_predict(p94, a, f94)
        ls.append(te)
        ic[a]["ic_v94"] = round(float(te[["pred", "y42"]].corr(method="spearman").iloc[0, 1]), 4)
        print(a, ic[a], flush=True)
    ls = pd.concat(ls, ignore_index=True)
    W_lo, W94 = v92.weights_from(lo, "model"), v94.weights_ls(ls, True)
    out = {"version": "v113", "first_rows": first, "ic": ic}
    out["v92_long_only"] = v103.evaluate(panel, W_lo, "v113 v92 LO", scale=v92.vol_target_scale(panel, W_lo))
    out["v94_long_short"] = v103.evaluate(panel, W94, "v113 v94 LS", scale=v94.vol_target_scale(panel, W94))
    idx = W_lo.index.union(W94.index)
    W96 = 0.5 * W_lo.reindex(idx).fillna(0.0).mul(v92.vol_target_scale(panel, W_lo).reindex(idx).fillna(1.0), axis=0) \
        + 0.5 * W94.reindex(idx).fillna(0.0).mul(v94.vol_target_scale(panel, W94).reindex(idx).fillna(1.0), axis=0)
    out["primary_v96_blend"] = v103.evaluate(panel, W96, "v113 v96 blend", scale=1.0)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v113_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
