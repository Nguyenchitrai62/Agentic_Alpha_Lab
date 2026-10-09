"""Compute causal top-trader LS-ratio contrarian gates per coin (frozen PLAN.md).

Per 4h close T on the standard grid: LS(T) = last
count_toptrader_long_short_ratio with create_time <= T-5min (5-min lag, causal
asof; NaN where missing/non-finite/non-positive, never imputed).
Per-anchor p90/p10 over LS in [A-372d, A-7d) (>=1000 finite else NaN) ->
gate_long (LS > p90) / gate_short (LS < p10). Rows < 2021-09-24 never gated.

Usage:
  python compute_lsratio.py        # full build (resume-safe caches in tmp/)
Run directly or via heavy_slot (metrics working set > 0.4 GB).
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from lsratio_rule import MIN_NORM, anchor_of, asof_ratio

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OIDIR = ROOT / "data/raw/um_metrics_20260926"
TMP = HERE / "tmp"
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
ANCH = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
GRID_START = pd.Timestamp("2020-09-01 00:00", tz="UTC")
GRID_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
YEAR = pd.Timedelta(days=365)
EMBARGO = pd.Timedelta(days=7)
NORM_WIN = pd.Timedelta(days=372)
LS_LAG = pd.Timedelta(minutes=5)
CUTOFF = pd.Timestamp("2021-09-24", tz="UTC")
LS_COL = "count_toptrader_long_short_ratio"

HEARTBEAT_S = 600
_stop_hb = threading.Event()


def heartbeat(tag):
    while not _stop_hb.wait(HEARTBEAT_S):
        print(f"[hb {datetime.now(timezone.utc):%H:%M:%S}Z] {tag} alive", flush=True)


def ls_asof(sym: str, grid_ns: np.ndarray) -> np.ndarray:
    """LS(T) per grid bar via causal asof (<= T-5min), one coin at a time."""
    m = pd.read_parquet(OIDIR / f"{sym}_metrics.parquet",
                         columns=["create_time", LS_COL])
    m["create_time"] = pd.to_datetime(m["create_time"], utc=True)
    m = m.drop_duplicates("create_time").sort_values("create_time")
    ot = m["create_time"].values.astype("datetime64[ns]").astype(np.int64)
    ov = m[LS_COL].to_numpy(dtype=np.float32).astype(float)
    del m
    q = grid_ns - LS_LAG.value
    return asof_ratio(ot, ov, q)


def main() -> None:
    TMP.mkdir(parents=True, exist_ok=True)
    hb = threading.Thread(target=heartbeat, args=("compute_lsratio",), daemon=True)
    hb.start()
    try:
        grid = pd.date_range(GRID_START, GRID_END, freq="4h", tz="UTC")
        grid_ns = grid.values.astype("datetime64[ns]").astype(np.int64)
        panel = pd.DataFrame({"T": grid})
        for sym in MAJORS:
            ls = ls_asof(sym, grid_ns)
            panel[f"LS_{sym}"] = ls.astype(np.float32)
            print(f"{sym}: LS finite={int(np.isfinite(ls).sum())}/{len(ls)}",
                  flush=True)
        panel.to_parquet(TMP / "lsratio_panel_raw.parquet", index=False)

        T = pd.to_datetime(panel["T"], utc=True)
        anch = [pd.Timestamp(a, tz="UTC") for a in ANCH]
        gates = pd.DataFrame({"T": T})
        norms: dict = {}
        for sym in MAJORS:
            ls = panel[f"LS_{sym}"].to_numpy(dtype=float)
            p90_arr = np.full(len(T), np.nan)
            p10_arr = np.full(len(T), np.nan)
            gl = np.zeros(len(T), dtype=bool)
            gs = np.zeros(len(T), dtype=bool)
            ninfo = {}
            for y, A in enumerate(anch):
                lo, hi = A - NORM_WIN, A - EMBARGO
                m = (T >= lo) & (T < hi)
                w = ls[m.values]
                w = w[np.isfinite(w) & (w > 0)]
                ninfo[str(A.date())] = int(w.size)
                if w.size < MIN_NORM:
                    continue
                p90, p10 = float(np.percentile(w, 90.0)), float(np.percentile(w, 10.0))
                norms.setdefault(sym, {})[str(A.date())] = {
                    "p90": p90, "p10": p10, "n": int(w.size)}
                yy = np.array([anchor_of(t) for t in T]) == y
                p90_arr[yy] = p90
                p10_arr[yy] = p10
                f = np.isfinite(ls[yy]) & (ls[yy] > 0)
                gl[yy] = f & (ls[yy] > p90)
                gs[yy] = f & (ls[yy] < p10)
            pre = (T < CUTOFF).to_numpy()
            gl[pre] = False
            gs[pre] = False
            gates[f"long_{sym}"] = gl
            gates[f"short_{sym}"] = gs
            panel[f"p90_{sym}"] = p90_arr
            panel[f"p10_{sym}"] = p10_arr
            print(f"{sym} norms n={ninfo} long/yr=" +
                  str(pd.Series(gl, index=T).groupby(
                      [anchor_of(t) for t in T]).sum().to_dict()) +
                  " short/yr=" + str(pd.Series(gs, index=T).groupby(
                      [anchor_of(t) for t in T]).sum().to_dict()), flush=True)
        panel.to_parquet(TMP / "lsratio_panel.parquet", index=False)
        gates.to_parquet(TMP / "gates_std.parquet", index=False)
        (TMP / "norms.json").write_text(json.dumps(norms, indent=1))
        print("norms:", json.dumps(norms, indent=1), flush=True)
        lcols = [c for c in gates.columns if c.startswith("long_")]
        scols = [c for c in gates.columns if c.startswith("short_")]
        print(f"gate rates: long={gates[lcols].to_numpy().mean():.5f} "
              f"short={gates[scols].to_numpy().mean():.5f} n={len(gates)}",
              flush=True)
    finally:
        _stop_hb.set()


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"compute_lsratio done {(time.time()-t0)/60:.1f}min", flush=True)
