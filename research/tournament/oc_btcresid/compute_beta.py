"""oc_btcresid beta computation (frozen PLAN.md definitions).

hourly_ext -> 4h closes on the standard grid -> 4h log returns ->
per-anchor OLS betas over [A-372d, A-7d) -> betas.json + controls.json.

Causality: C4(T) uses the hourly bar starting at T-1h (END <= T);
r(T) = log(C4(T)/C4(T-4h)); betas use only return pairs ending in
[A-372d, A-7d). Residuals/controls are derived in run_engine.py from
betas.json on the standard grid (post-bear, pre-ffill).

Usage:
  python compute_beta.py        # full build (resume-safe caches in tmp/)
Run via heavy_slot when RAM is tight (hourly parquet > 0.4 GB working set).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from resid_rule import ANCH5, COINS, anchor_of, control_mult, ols_beta

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"
TMP = HERE / "tmp"
MAJORS = list(COINS)
GRID_START = pd.Timestamp("2020-08-04 00:00", tz="UTC")
GRID_END = pd.Timestamp("2026-09-23 20:00", tz="UTC")
YEAR = pd.Timedelta(days=365)
EMBARGO = pd.Timedelta(days=7)
NORM_WIN = pd.Timedelta(days=372)
MIN_PAIRS = 100
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
    need = grid - pd.Timedelta(hours=1)
    sub = piv.reindex(need)
    sub.index = grid
    return sub


def compute_rets(c4: pd.DataFrame) -> pd.DataFrame:
    """4h log returns on the standard grid (causal; NaN where undefined)."""
    closes = c4[MAJORS].to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        rets = np.log(closes[1:] / closes[:-1])
    rets[~np.isfinite(rets)] = np.nan
    out = pd.DataFrame(np.vstack([np.full((1, len(MAJORS)), np.nan), rets]),
                       index=c4.index, columns=MAJORS)
    return out


def main() -> None:
    TMP.mkdir(parents=True, exist_ok=True)
    h = pd.read_parquet(HOURLY, columns=["t", "close", "sym"])
    c4 = build_4h_closes(h)
    del h
    rets = compute_rets(c4)
    rets.to_parquet(TMP / "rets_std.parquet", index=True)
    c4.to_parquet(TMP / "c4_std.parquet", index=True)

    anch = [pd.Timestamp(a, tz="UTC") for a in ANCH5]
    T = c4.index
    T_ns = T.values.astype("datetime64[ns]").astype(np.int64)
    rbtc = rets["BTCUSDT"].to_numpy(dtype=float)

    betas: dict[str, dict[str, float]] = {}
    for A in anch:
        lo = A - NORM_WIN
        hi = A - EMBARGO
        m = (T >= lo) & (T < hi)
        row: dict[str, float] = {"BTCUSDT": 1.0}
        for c in MAJORS:
            if c == "BTCUSDT":
                continue
            rc = rets[c].to_numpy(dtype=float)[m]
            xb = rbtc[m]
            b = ols_beta(xb, rc)
            row[c] = float(b) if np.isfinite(b) else float("nan")
        betas[str(A.date())] = row
    (TMP / "betas.json").write_text(json.dumps(
        {"betas": betas, "min_pairs": MIN_PAIRS,
         "window": "[A-372d, A-7d)", "returns": "log 4h"}, indent=1))

    # realised gross-exposure placeholder: run_engine.py computes the true
    # post-bear means from sb and overwrites controls.json; here store NaN
    # markers so the file exists with the frozen schema.
    controls = {str(A.date()): {"m_c1": float("nan"), "m_c2": float("nan"),
                                "n_bars": 0} for A in anch}
    (TMP / "controls.json").write_text(json.dumps(controls, indent=1))
    print("betas:", json.dumps(betas, indent=1), flush=True)
    print(f"n_grid={len(T)} grid=[{T[0]}, {T[-1]}]", flush=True)


if __name__ == "__main__":
    main()
