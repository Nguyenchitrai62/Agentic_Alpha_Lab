"""oc_spillgate gate computation (frozen PLAN.md definitions).

hourly_ext -> 4h closes on the standard grid -> c(T), d(T) -> per-anchor
q90/q95 over [A-372d, A-7d) -> gate tables + control constants.

Causality: C4(T) uses the hourly bar starting at T-1h (END <= T);
r(T) = log(C4(T)/C4(T-4h)); c(T) uses the 6 returns ending <= T;
d(T) = c(T) - c(T-24h). Thresholds use only T in [A-372d, A-7d).

Usage:
  python compute_spill.py        # full build (resume-safe caches in tmp/)
Run directly (hourly parquet ~1.8M rows, float32, one process) or via
heavy_slot when RAM is tight.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from spill_rule import ANCH5, anchor_of, control_mult, pairwise_mean_corr

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"
TMP = HERE / "tmp"
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
GRID_START = pd.Timestamp("2020-08-04 00:00", tz="UTC")
GRID_END = pd.Timestamp("2026-09-23 20:00", tz="UTC")
YEAR = pd.Timedelta(days=365)
EMBARGO = pd.Timedelta(days=7)
NORM_WIN = pd.Timedelta(days=372)
MIN_NORM = 1000
CUTOFF = pd.Timestamp("2021-09-24", tz="UTC")


def build_4h_closes(h: pd.DataFrame) -> pd.DataFrame:
    """Pivot hourly to 4h standard-grid closes (float32).

    C4(sym, T) = hourly close of the bar starting at T-1h (END <= T).
    """
    h = h[h["sym"].isin(MAJORS)].copy()
    h["t"] = pd.to_datetime(h["t"], utc=True)
    piv = h.pivot(index="t", columns="sym", values="close").sort_index()
    for c in MAJORS:
        if c not in piv.columns:
            piv[c] = np.nan
    piv = piv[MAJORS].astype(np.float32)
    grid = pd.date_range(GRID_START, GRID_END, freq="4h", tz="UTC")
    # hourly bar start needed for 4h close T is T-1h
    need = grid - pd.Timedelta(hours=1)
    sub = piv.reindex(need)
    sub.index = grid
    return sub


def compute_cd(c4: pd.DataFrame) -> pd.DataFrame:
    """c(T), d(T) per standard-grid bar (causal; NaN where undefined)."""
    closes = c4[MAJORS].to_numpy(dtype=float)
    rets = np.log(closes[1:] / closes[:-1])
    rets[~np.isfinite(rets)] = np.nan
    # rets[k] ends at grid[k+1]; c at grid t uses last 6 rets ending <= t
    n = len(c4)
    c = np.full(n, np.nan)
    for t in range(n):
        # returns with end in (T-24h, T]: indices (t-6, t] in rets space
        # rets index k ends at grid k+1, so need k+1 in (t-6, t] -> k in [t-6, t-1]
        lo, hi = t - 6, t - 1
        if lo < 0:
            continue
        R = rets[lo:hi + 1]
        if R.shape[0] != 6:
            continue
        c[t] = pairwise_mean_corr(R)
    d = np.full(n, np.nan)
    d[6:] = c[6:] - c[:-6]
    out = pd.DataFrame({"T": c4.index, "c": c, "d": d})
    return out


def main() -> None:
    TMP.mkdir(parents=True, exist_ok=True)
    h = pd.read_parquet(HOURLY, columns=["t", "close", "sym"])
    c4 = build_4h_closes(h)
    del h
    cd = compute_cd(c4)
    cd.to_parquet(TMP / "cd_std.parquet", index=False)

    anch = [pd.Timestamp(a, tz="UTC") for a in ANCH5]
    anch_ns = np.array([a.value for a in anch], dtype=np.int64)
    T = pd.to_datetime(cd["T"], utc=True)
    T_ns = T.values.astype("datetime64[ns]").astype(np.int64)
    c = cd["c"].to_numpy(dtype=float)
    d = cd["d"].to_numpy(dtype=float)

    thresholds = {}
    for i, A in enumerate(anch):
        lo = A - NORM_WIN
        hi = A - EMBARGO
        m = (T >= lo) & (T < hi)
        pc = c[m]
        pd_ = d[m]
        pc = pc[np.isfinite(pc)]
        pd_ = pd_[np.isfinite(pd_)]
        q90 = float(np.quantile(pc, 0.90)) if len(pc) >= MIN_NORM else float("nan")
        q95 = float(np.quantile(pd_, 0.95)) if len(pd_) >= MIN_NORM else float("nan")
        thresholds[str(A.date())] = {
            "q90": q90, "q95": q95,
            "n_c": int(len(pc)), "n_d": int(len(pd_)),
        }
    (TMP / "thresholds.json").write_text(json.dumps(thresholds, indent=1))

    y = anchor_of(T_ns, anch_ns)
    q90v = np.array([thresholds[str(anch[i].date())]["q90"] for i in y])
    q95v = np.array([thresholds[str(anch[i].date())]["q95"] for i in y])
    s1 = np.isfinite(c) & np.isfinite(q90v) & (c > q90v)
    s2 = np.isfinite(d) & np.isfinite(q95v) & (d > q95v)
    pre = (T < CUTOFF).to_numpy()
    s1[pre] = False
    s2[pre] = False
    gates = pd.DataFrame({"T": T, "s1": s1, "s2": s2,
                          "c": c, "d": d})
    gates.to_parquet(TMP / "gates_std.parquet", index=False)

    controls = {}
    for i, A in enumerate(anch):
        m = (T >= A) & (T < A + YEAR)
        sh1 = float(s1[m].mean()) if int(m.sum()) else 0.0
        sh2 = float(s2[m].mean()) if int(m.sum()) else 0.0
        controls[str(A.date())] = {
            "share_s1": sh1, "share_s2": sh2,
            "m_c1": control_mult(sh1), "m_c2": control_mult(sh2),
            "n_bars": int(m.sum()),
        }
    (TMP / "controls.json").write_text(json.dumps(controls, indent=1))
    print("thresholds:", json.dumps(thresholds, indent=1), flush=True)
    print("controls:", json.dumps(controls, indent=1), flush=True)
    print(f"gate rates: s1={s1.mean():.4f} s2={s2.mean():.4f} n={len(s1)}", flush=True)


if __name__ == "__main__":
    main()
