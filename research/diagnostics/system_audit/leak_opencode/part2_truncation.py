"""Part 2: truncation tests for tv_indicators.tv_features and flow_features on order-level table."""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from leak_checks import truncate_compare

HERE = Path(__file__).parent
RD = Path("research/parallel/rounds/parallel-20260906-r2")
RNG = np.random.default_rng(7)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def pick_times(n=20):
    lo, hi = pd.Timestamp("2022-01-01", tz="UTC"), pd.Timestamp("2026-09-01", tz="UTC")
    span = (hi - lo).total_seconds()
    ts = sorted(lo + pd.to_timedelta(RNG.uniform(0, span, n), unit="s") for _ in range(0))
    ts = sorted([lo + pd.Timedelta(seconds=float(s)) for s in RNG.uniform(0, span, n)])
    # snap down to 4h grid (decision index t = bar open; close = t+4h)
    return sorted({pd.Timestamp(t).floor("4h") for t in ts})


def test_tv(times):
    tv = _load("tv_audit", RD / "v231/tv_indicators.py")
    v92 = _load("v92_audit", RD / "v92/v92_pooled_hgb_vt.py")
    b, _, _ = v92.load_asset("BTCUSDT")  # 4h bars, has open_time
    b = b.sort_values("open_time").reset_index(drop=True)
    out, t0 = [], time.time()
    for T in times:
        close = T + pd.Timedelta(hours=4)
        full = b[b["open_time"] <= b["open_time"].max()].copy()
        trunc = b[b["open_time"] <= T].copy()
        if len(trunc) < 600:
            out.append({"T": str(T), "status": "skip-short-history", "bad": [], "maxdiff": ""})
            continue
        f_full = tv.tv_features(full)
        f_tr = tv.tv_features(trunc)
        # row at T: position of T in each frame
        i_full = full.index[full["open_time"] == T]
        if len(i_full) == 0:
            out.append({"T": str(T), "status": "T-not-a-bar", "bad": [], "maxdiff": ""})
            continue
        i = int(i_full[0])
        ok, bad, md = truncate_compare(f_full.iloc[[i]], f_tr.iloc[[-1]])
        out.append({"T": str(T), "status": "ok" if ok else "MISMATCH", "bad": bad, "maxdiff": md})
    return out, round(time.time() - t0, 1)


def test_flow_orders(times):
    fl = _load("flow_audit", RD / "v236/flow_features.py")
    fl.D = Path("data/raw/aggflow_20260928_orders")
    syms = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    out, t0 = [], time.time()
    for T in times:
        close = T + pd.Timedelta(hours=4)
        bad_all, md_max, tested = [], 0.0, []
        for s in syms:
            arch = pd.read_parquet(fl.D / f"{s}_flow_4h.parquet").sort_index()
            grid = pd.date_range(arch.index[0], arch.index[-1], freq="4h", tz="UTC")
            bar_open = grid[grid <= T][-600:] if (grid <= T).any() else grid[:0]
            if len(bar_open) < 100:
                continue
            f_full = fl.flow_features(s, bar_open)
            trunc_frame = arch[arch.index <= close]
            f_tr = fl.flow_features(s, bar_open, frame=trunc_frame)
            ok, bad, md = truncate_compare(f_full.iloc[[-1]], f_tr.iloc[[-1]])
            tested.append(s)
            bad_all += [f"{s}:{c}" for c in bad]
            md_max = max(md_max, md if md == md else 0.0)
        out.append({"T": str(T), "symbols": tested, "status": "ok" if not bad_all else "MISMATCH",
                    "bad": bad_all, "maxdiff": md_max})
    return out, round(time.time() - t0, 1)


def main():
    times = pick_times(20)
    tv_res, tv_t = test_tv(times)
    fl_res, fl_t = test_flow_orders(times)
    out = {"times": [str(t) for t in times], "tv_seconds": tv_t, "flow_seconds": fl_t,
           "tv": tv_res, "flow_orders": fl_res}
    (HERE / "part2_truncation.json").write_text(json.dumps(out, indent=1, default=str))
    print(f"part2 done: tv {tv_t}s mismatches={sum(1 for r in tv_res if r['status']=='MISMATCH')}, "
          f"flow {fl_t}s mismatches={sum(1 for r in fl_res if r['status']=='MISMATCH')}")


if __name__ == "__main__":
    main()
