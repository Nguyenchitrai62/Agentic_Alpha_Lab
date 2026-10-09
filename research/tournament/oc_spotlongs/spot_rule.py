"""oc_spotlongs pure rules: funding signal F7, pre-anchor medians, routing, borrow.

All definitions frozen in PLAN.md. Everything here is causal:
- F7[T, s] uses only settlements with c < T (millisecond-exact, [T-7d, T)).
- med_k[s] uses only bar times in [2020-01-01, A_k - 7d) (7-day embargo).
- borrow_bar uses only the current bar's end quantities and bar-start equity.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
FUND_DIR = ROOT / "data/raw/binance_premium_20260928"
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
FEAT_START = pd.Timestamp("2020-01-01", tz="UTC")
EMBARGO = pd.Timedelta(days=7)
WIN = pd.Timedelta(days=7)
MIN_SETTLE = 14
HRS_YR = 365.0 * 24.0


def load_funding(syms=SYMS) -> dict[str, pd.DataFrame]:
    """{sym: DataFrame(calc_time UTC, rate)} sorted, millisecond-exact stamps."""
    out = {}
    for s in syms:
        df = pd.read_parquet(FUND_DIR / f"{s}_funding.parquet",
                             columns=["calc_time", "last_funding_rate"])
        t = pd.to_datetime(df["calc_time"], utc=True)
        r = df["last_funding_rate"].to_numpy(dtype=float)
        o = np.argsort(t.values.astype("datetime64[ns]").astype(np.int64))
        out[s] = pd.DataFrame({"c": t.to_numpy()[o], "r": r[o]})
    return out


def f7_at(T: np.ndarray, c_ns: np.ndarray, r: np.ndarray) -> np.ndarray:
    """Mean rate over settlements with T-7d <= c < T; NaN when < 14 in window.

    T: int64 ns array. Strictly-before-T via side='left' (a settlement stamped
    exactly at T is NOT usable at T).
    """
    lo = T - WIN.value
    i0 = np.searchsorted(c_ns, lo, side="left")
    i1 = np.searchsorted(c_ns, T, side="left")
    n = i1 - i0
    out = np.full(len(T), np.nan)
    cs = np.concatenate([[0.0], np.cumsum(r)])
    ok = n >= MIN_SETTLE
    out[ok] = (cs[i1[ok]] - cs[i0[ok]]) / n[ok]
    return out


def medians(fund: dict[str, pd.DataFrame] | None = None) -> dict[str, dict[str, float]]:
    """med_k[sym] = median of F7 over 4h bar times in [2020-01-01, A_k - 7d).

    Bar grid = shift-0 phase (every 4h from 2020-01-01 00:00 UTC). Fixed here,
    causal (strictly pre-anchor minus embargo), no test-year data.
    """
    fund = load_funding() if fund is None else fund
    out: dict[str, dict[str, float]] = {}
    for a in ANCH5:
        cut = pd.Timestamp(a, tz="UTC") - EMBARGO
        grid = pd.date_range(FEAT_START, cut, freq="4h")
        Tn = grid.values.astype("datetime64[ns]").astype(np.int64)
        row = {}
        for s, df in fund.items():
            c_ns = df["c"].values.astype("datetime64[ns]").astype(np.int64)
            f7 = f7_at(Tn, c_ns, df["r"].to_numpy())
            f7 = f7[np.isfinite(f7)]
            row[s] = float(np.median(f7)) if len(f7) else float("nan")
        out[a] = row
    return out


def route_matrix(T_list: list, syms: list[str], y_of: np.ndarray,
                 meds: dict[str, dict[str, float]],
                 fund: dict[str, pd.DataFrame]) -> np.ndarray:
    """Bool [n, na]: True = spot-route (finite F7 and F7 > pre-anchor median)."""
    Tn = np.array([pd.Timestamp(t).value for t in T_list])
    n, na = len(T_list), len(syms)
    out = np.zeros((n, na), bool)
    for j, s in enumerate(syms):
        df = fund[s]
        c_ns = df["c"].values.astype("datetime64[ns]").astype(np.int64)
        f7 = f7_at(Tn, c_ns, df["r"].to_numpy())
        for i in range(n):
            if not np.isfinite(f7[i]):
                continue
            med = meds[ANCH5[int(y_of[i])]][s]
            if np.isfinite(med) and f7[i] > med:
                out[i, j] = True
    return out


def borrow_bar(long_spot_frac: float, apr: float) -> float:
    """USDT borrow cost for one 4h bar (fraction of bar-start equity).

    B = max(0, spot long notional - equity); cost = B * APR * 4/8760.
    Cash covers the unleveraged part (no borrow when long <= equity).
    """
    if not (apr and np.isfinite(long_spot_frac)):
        return 0.0
    return max(0.0, float(long_spot_frac) - 1.0) * float(apr) * (4.0 / HRS_YR)
