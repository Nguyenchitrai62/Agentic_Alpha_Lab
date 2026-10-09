"""Compute causal OI-short-cover gates per coin (frozen PLAN.md definitions).

hourly_ext -> 4h closes C4(T) on the standard grid -> R24, sg per (T,sym).
um_metrics_20260926 OI as-of (5-min lag) -> dOI per (T,sym).
Per-anchor mu/sd over dOI in [A-372d, A-7d) -> z -> gate_O1 (z>2) / gate_O2 (z>1.5)
each AND R24 < -2*sg. Rows < 2021-09-24 never gated.

Usage:
  python compute_oishort.py        # full build (resume-safe caches in tmp/)
Run directly or via heavy_slot (hourly+OI working set > 0.4 GB).
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from oishort_rule import MIN_NORM, anchor_of, gate_short

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"
OIDIR = ROOT / "data/raw/um_metrics_20260926"
TMP = HERE / "tmp"
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
ANCH = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
GRID_START = pd.Timestamp("2020-09-01 00:00", tz="UTC")
GRID_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
YEAR = pd.Timedelta(days=365)
EMBARGO = pd.Timedelta(days=7)
NORM_WIN = pd.Timedelta(days=372)
OI_LAG = pd.Timedelta(minutes=5)
OI_LOOKBACK = pd.Timedelta(hours=24)
CUTOFF = pd.Timestamp("2021-09-24", tz="UTC")
OI_COL = "sum_open_interest"

HEARTBEAT_S = 600
_stop_hb = threading.Event()


def heartbeat(tag):
    while not _stop_hb.wait(HEARTBEAT_S):
        print(f"[hb {datetime.now(timezone.utc):%H:%M:%S}Z] {tag} alive", flush=True)


def build_4h_closes(h: pd.DataFrame) -> pd.DataFrame:
    """C4(sym, T) = hourly close of the bar starting at T-1h (END <= T). float32."""
    h = h[h["sym"].isin(MAJORS)].copy()
    h["t"] = pd.to_datetime(h["t"], utc=True)
    piv = h.pivot(index="t", columns="sym", values="close").sort_index()
    for c in MAJORS:
        if c not in piv.columns:
            piv[c] = np.nan
    piv = piv[MAJORS].astype(np.float32)
    grid = pd.date_range(GRID_START, GRID_END, freq="4h", tz="UTC")
    need = grid - pd.Timedelta(hours=1)
    sub = piv.reindex(need)
    sub.index = grid
    return sub


def price_legs(c4: pd.DataFrame):
    """R24, sg per (T, sym), causal. Returns dict sym -> (R24, sg) arrays."""
    grid = c4.index
    n = len(grid)
    out = {}
    closes = {}
    for sym in MAJORS:
        closes[sym] = c4[sym].to_numpy(dtype=float)
    for sym in MAJORS:
        C = closes[sym]
        with np.errstate(divide="ignore", invalid="ignore"):
            rets = np.log(C[1:] / C[:-1])
        rets[~np.isfinite(rets)] = np.nan
        # R24: ln(C[t]/C[t-6])
        R24 = np.full(n, np.nan)
        with np.errstate(divide="ignore", invalid="ignore"):
            prev = np.full(n, np.nan)
            prev[6:] = C[:-6]
            m = np.isfinite(C) & np.isfinite(prev) & (C > 0) & (prev > 0)
            R24[m] = np.log(C[m] / prev[m])
        # sg: std of 360 rets strictly before T -> rets[t-360:t] (rets index k ends at grid k+1)
        sg = np.full(n, np.nan)
        for t in range(n):
            lo, hi = t - 360, t - 1  # rets indices [lo, hi] (hi = t-1 ends at grid t)
            if hi < 0:
                continue
            lo = max(lo, 0)
            seg = rets[lo:hi + 1]
            seg = seg[np.isfinite(seg)]
            if seg.size < 120:
                continue
            sd = float(np.std(seg, ddof=1))
            if np.isfinite(sd) and sd > 0:
                sg[t] = sd
        out[sym] = (R24, sg)
    return out


def oi_doi(sym: str, grid_ns: np.ndarray) -> np.ndarray:
    """dOI(T) = ln(OI<=T-5min / OI<=T-24h-5min), NaN where undefined."""
    m = pd.read_parquet(OIDIR / f"{sym}_metrics.parquet",
                         columns=["create_time", OI_COL])
    m["create_time"] = pd.to_datetime(m["create_time"], utc=True)
    m = m.drop_duplicates("create_time").sort_values("create_time")
    ot = m["create_time"].values.astype("datetime64[ns]").astype(np.int64)
    ov = m[OI_COL].to_numpy(dtype=float)
    lag = OI_LAG.value
    h24 = OI_LOOKBACK.value
    q_now = grid_ns - lag
    q_24 = grid_ns - h24 - lag
    i_now = np.searchsorted(ot, q_now, side="right") - 1
    i_24 = np.searchsorted(ot, q_24, side="right") - 1
    n = len(grid_ns)
    dOI = np.full(n, np.nan)
    ok = (i_now >= 0) & (i_24 >= 0)
    o_now = np.full(n, np.nan)
    o_24 = np.full(n, np.nan)
    o_now[ok] = ov[i_now[ok]]
    o_24[ok] = ov[i_24[ok]]
    good = ok & np.isfinite(o_now) & np.isfinite(o_24) & (o_now > 0) & (o_24 > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        dOI[good] = np.log(o_now[good] / o_24[good])
    return dOI


def main() -> None:
    TMP.mkdir(parents=True, exist_ok=True)
    hb = threading.Thread(target=heartbeat, args=("compute_oishort",), daemon=True)
    hb.start()
    try:
        cache_c4 = TMP / "c4_std.parquet"
        if cache_c4.exists():
            c4 = pd.read_parquet(cache_c4)
            c4.index = pd.to_datetime(c4.index, utc=True)
            print("loaded cached c4", c4.shape, flush=True)
        else:
            h = pd.read_parquet(HOURLY, columns=["t", "close", "sym"])
            c4 = build_4h_closes(h)
            del h
            c4.to_parquet(cache_c4)
            print("built c4", c4.shape, flush=True)
        grid = c4.index
        grid_ns = grid.values.astype("datetime64[ns]").astype(np.int64)
        plegs = price_legs(c4)

        panel = pd.DataFrame({"T": grid})
        norms = {}
        for sym in MAJORS:
            dOI = oi_doi(sym, grid_ns)
            R24, sg = plegs[sym]
            panel[f"dOI_{sym}"] = dOI
            panel[f"R24_{sym}"] = R24
            panel[f"sg_{sym}"] = sg
            print(f"{sym}: dOI finite={int(np.isfinite(dOI).sum())}/{len(dOI)} "
                  f"R24 finite={int(np.isfinite(R24).sum())} "
                  f"sg finite={int(np.isfinite(sg).sum())}", flush=True)
        panel.to_parquet(TMP / "oishort_panel_raw.parquet", index=False)

        # per-anchor norms on dOI + gates
        T = pd.to_datetime(panel["T"], utc=True)
        anch = [pd.Timestamp(a, tz="UTC") for a in ANCH]
        gates = pd.DataFrame({"T": T})
        for sym in MAJORS:
            dOI = panel[f"dOI_{sym}"].to_numpy(dtype=float)
            R24 = panel[f"R24_{sym}"].to_numpy(dtype=float)
            sg = panel[f"sg_{sym}"].to_numpy(dtype=float)
            mu_arr = np.full(len(T), np.nan)
            sd_arr = np.full(len(T), np.nan)
            z_arr = np.full(len(T), np.nan)
            o1 = np.zeros(len(T), dtype=bool)
            o2 = np.zeros(len(T), dtype=bool)
            ninfo = {}
            for y, A in enumerate(anch):
                lo, hi = A - NORM_WIN, A - EMBARGO
                m = (T >= lo) & (T < hi)
                w = dOI[m.values]
                w = w[np.isfinite(w)]
                ninfo[str(A.date())] = int(w.size)
                if w.size < MIN_NORM:
                    continue
                mu, sd = float(w.mean()), float(w.std(ddof=1))
                norms.setdefault(sym, {})[str(A.date())] = {
                    "mu": mu, "sd": sd, "n": int(w.size)}
                yy = np.array([anchor_of(t) for t in T]) == y
                mu_arr[yy] = mu
                sd_arr[yy] = sd
                with np.errstate(divide="ignore", invalid="ignore"):
                    zz = (dOI[yy] - mu) / sd if sd > 1e-12 else np.full(yy.sum(), np.nan)
                z_arr[yy] = zz
                price_ok = (np.isfinite(R24[yy]) & np.isfinite(sg[yy]) & (sg[yy] > 0)
                            & (R24[yy] < -2.0 * sg[yy]))
                o1[yy] = np.isfinite(zz) & (zz > 2.0) & price_ok
                o2[yy] = np.isfinite(zz) & (zz > 1.5) & price_ok
            pre = (T < CUTOFF).to_numpy()
            o1[pre] = False
            o2[pre] = False
            gates[f"o1_{sym}"] = o1
            gates[f"o2_{sym}"] = o2
            panel[f"mu_{sym}"] = mu_arr
            panel[f"sd_{sym}"] = sd_arr
            panel[f"z_{sym}"] = z_arr
            print(f"{sym} norms n={ninfo} gates/yr O1=" +
                  str(pd.Series(o1, index=T).groupby(
                      [anchor_of(t) for t in T]).sum().to_dict()) +
                  " O2=" + str(pd.Series(o2, index=T).groupby(
                      [anchor_of(t) for t in T]).sum().to_dict()), flush=True)
        panel.to_parquet(TMP / "oishort_panel.parquet", index=False)
        gates.to_parquet(TMP / "gates_std.parquet", index=False)
        (TMP / "norms.json").write_text(json.dumps(norms, indent=1))
        print("norms:", json.dumps(norms, indent=1), flush=True)
        print(f"gate rates: O1={gates[[c for c in gates.columns if c.startswith('o1_')]].to_numpy().mean():.5f} "
              f"O2={gates[[c for c in gates.columns if c.startswith('o2_')]].to_numpy().mean():.5f} "
              f"n={len(gates)}", flush=True)
    finally:
        _stop_hb.set()


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"compute_oishort done {(time.time()-t0)/60:.1f}min", flush=True)
