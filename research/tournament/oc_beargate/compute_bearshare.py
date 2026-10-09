"""oc_beargate bear share: which fraction of bars / fills sits in bear state?

Bars: per year y (all 4 shifts pooled), decision holding-bars T on each shift
grid [A+sh, min(A+sh+365d, live1)), step 4h, bear_state(T) via the exact v421
bear series ffilled <= T (causal).
Fills: D0-replica ledger rung fills (oc_k2placebo/tmp read-only, n == 22312):
each fill's holding-bar open (bt_all) mapped to bear_state the same way.
CPU-only.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
K2P = ROOT / "research/tournament/oc_k2placebo"

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
ANCH = [pd.Timestamp(a, tz="UTC") for a in ANCH5]
LIVE1 = pd.Timestamp("2026-09-23", tz="UTC")
N_GATE = 22312


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_bear():
    er = _load("er_bg_share", ROOT / "research/parallel/rounds/parallel-20260906-r2/engine_real/engine_real.py")
    books, opens = er.v154_books()
    btc = opens["BTCUSDT"].reindex(books.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).fillna(False).to_numpy(dtype=bool)
    idx_ns = books.index.values.astype("datetime64[ns]").astype(np.int64)
    order = np.argsort(idx_ns)
    return idx_ns[order], bear[order]


def bear_at_vec(bidx_ns, bval, ask_ns):
    pos = np.searchsorted(bidx_ns, ask_ns, side="right") - 1
    out = np.zeros(len(ask_ns), dtype=bool)
    ok = pos >= 0
    out[ok] = bval[np.clip(pos[ok], 0, len(bval) - 1)]
    return out


def main() -> None:
    bidx_ns, bval = build_bear()
    print(f"bear std grid n={len(bidx_ns)} bear_share_all={round(float(bval.mean()), 4)}", flush=True)

    per_year = []
    for y, a in enumerate(ANCH):
        T_all = []
        for sh in (0, 1, 2, 3):
            lo = a + pd.Timedelta(hours=sh)
            hi = min(a + pd.Timedelta(hours=sh) + pd.Timedelta(days=365), LIVE1 + pd.Timedelta(hours=sh))
            grid = pd.date_range(lo, hi, freq="4h", inclusive="left")
            T_all.extend(grid)
        T_all = pd.DatetimeIndex(T_all)
        ask = T_all.values.astype("datetime64[ns]").astype(np.int64)
        b = bear_at_vec(bidx_ns, bval, ask)
        per_year.append({"year": ANCH5[y], "n_bars": int(len(T_all)),
                         "bear_bars": int(b.sum()),
                         "bear_bar_share": round(float(b.mean()), 4)})
        print(per_year[-1], flush=True)

    # fills share from the replica ledger
    led = dict(np.load(K2P / "tmp/ledger.npz"))
    bt_all = np.load(K2P / "tmp/bt_all.npy", allow_pickle=True)
    n = len(led["w"])
    assert n == N_GATE, f"ledger size {n} != {N_GATE}"
    yr = led["year"].astype(int)
    bt_ts = pd.to_datetime(bt_all, utc=True)
    ask_f = bt_ts.values.astype("datetime64[ns]").astype(np.int64)
    bf = bear_at_vec(bidx_ns, bval, ask_f)
    fills = []
    for y in range(5):
        m = yr == y
        fills.append({"year": ANCH5[y], "n_fills": int(m.sum()),
                      "bear_fills": int(bf[m].sum()),
                      "bear_fill_share": round(float(bf[m].mean()), 4) if m.any() else None})
        print(fills[-1], flush=True)

    out = {"bars_per_year": per_year, "fills_per_year": fills,
           "note": "bear = v421_gross_cap.py:70 ffilled <= T (causal); bars = shift grids; fills = k2placebo replica ledger"}
    (HERE / "tmp/bearshare.json").write_text(json.dumps(out, indent=1))
    print("wrote tmp/bearshare.json", flush=True)


if __name__ == "__main__":
    main()
