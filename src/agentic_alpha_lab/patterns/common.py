"""Shared contract for pattern_lab_r1 feature workers.

Every feature module exposes::

    compute(bars) -> DataFrame   # float features, same index as bars
    events(bars)  -> DataFrame   # int {-1, 0, +1} directional hypotheses

Row ``t`` may use only ``bars.iloc[: t + 1]`` (closed bars). Use
``assert_causal`` in tests. Research code reads data only via ``load_bars``,
which by default stops before the opened 2025-09-24 year.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
from scipy import stats

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "ma_ribbon_20260924"
DEV_DATA_END = pd.Timestamp("2025-09-24", tz="UTC")  # bars opening at/after this are the opened year
DEV_DECISION_END = pd.Timestamp("2025-09-14", tz="UTC")  # decisions before this (10-day embargo)
DEV_SPLIT = pd.Timestamp("2022-09-01", tz="UTC")  # first/second half of development for stability checks
TIMEFRAMES = ("1h", "4h", "1d")


def load_bars(tf: str, include_opened_year: bool = False) -> pd.DataFrame:
    """Closed Binance USD-M BTCUSDT bars. Workers must keep the default."""
    if tf not in TIMEFRAMES:
        raise ValueError(tf)
    bars = pd.read_parquet(DATA_DIR / f"klines_{tf}.parquet").sort_values("open_time").reset_index(drop=True)
    if not include_opened_year:
        bars = bars.loc[bars["open_time"] < DEV_DATA_END].reset_index(drop=True)
    return bars


def load_funding(include_opened_year: bool = False) -> pd.DataFrame:
    f = pd.read_parquet(DATA_DIR / "funding.parquet").sort_values("fundingTime").reset_index(drop=True)
    if not include_opened_year:
        f = f.loc[f["fundingTime"] < DEV_DATA_END].reset_index(drop=True)
    return f


def assert_causal(fn: Callable[[pd.DataFrame], pd.DataFrame], bars: pd.DataFrame, cuts: tuple[int, ...] | None = None) -> None:
    """Rows <= cut must be identical when computed on bars truncated at cut."""
    full = fn(bars)
    assert len(full) == len(bars) and full.index.equals(bars.index), "output must align with bars"
    n = len(bars)
    for cut in cuts or (n // 3, n // 2, (3 * n) // 4, n - 2):
        part = fn(bars.iloc[: cut + 1].copy())
        pd.testing.assert_frame_equal(
            full.iloc[: cut + 1].reset_index(drop=True),
            part.reset_index(drop=True),
            check_dtype=False,
            obj=f"causality at cut={cut}",
        )


def forward_log_return(bars: pd.DataFrame, h: int) -> pd.Series:
    """log(open[t+1+h] / open[t+1]): entry at next open, exit h bars later."""
    o = bars["open"]
    return np.log(o.shift(-(1 + h)) / o.shift(-1))


def newey_west_t(x: np.ndarray, lag: int) -> float:
    x = np.asarray(x, float)
    n = len(x)
    if n < 3:
        return float("nan")
    d = x - x.mean()
    var = d @ d / n
    for k in range(1, min(lag, n - 1) + 1):
        w = 1 - k / (lag + 1)
        var += 2 * w * (d[k:] @ d[:-k]) / n
    return float(x.mean() / np.sqrt(var / n)) if var > 0 else float("nan")


def benjamini_hochberg(p: np.ndarray) -> np.ndarray:
    p = np.asarray(p, float)
    q = np.full_like(p, np.nan)
    ok = ~np.isnan(p)
    pv = p[ok]
    order = np.argsort(pv)
    ranked = pv[order] * len(pv) / (np.arange(len(pv)) + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty_like(pv)
    out[order] = np.minimum(ranked, 1.0)
    q[ok] = out
    return q


def event_study(
    bars: pd.DataFrame, events: pd.DataFrame, horizons: tuple[int, ...] = (1, 3, 6, 12), tf: str = ""
) -> pd.DataFrame:
    """Signed forward return after each event vs the unconditional mean (development decisions only).

    Excess for an event at t with direction d: d * (r_h[t] - mean(r_h)). Newey-West lag = h.
    """
    decide = (bars["open_time"] < DEV_DECISION_END).to_numpy()
    first_half = (bars["open_time"] < DEV_SPLIT).to_numpy()
    rows = []
    for h in horizons:
        r = forward_log_return(bars, h).to_numpy()
        valid = decide & ~np.isnan(r)
        base = np.nanmean(r[valid])
        for col in events.columns:
            d = events[col].to_numpy()
            m = valid & (d != 0)
            if m.sum() == 0:
                continue
            ex = d[m] * (r[m] - base)
            t = newey_west_t(ex, h)
            halves = [ex[first_half[m]], ex[~first_half[m]]]
            rows.append(dict(
                tf=tf, pattern=col, horizon=h, n=int(m.sum()), n_long=int((d[m] > 0).sum()),
                n_short=int((d[m] < 0).sum()), mean_excess_bps=1e4 * ex.mean(),
                hit_rate=float(np.mean(d[m] * r[m] > 0)), nw_t=t,
                p_value=float(2 * stats.norm.sf(abs(t))) if np.isfinite(t) else np.nan,
                first_half_bps=1e4 * halves[0].mean() if len(halves[0]) else np.nan,
                second_half_bps=1e4 * halves[1].mean() if len(halves[1]) else np.nan,
            ))
    out = pd.DataFrame(rows)
    if len(out):
        out["q_value"] = benjamini_hochberg(out["p_value"].to_numpy())
        out["stable_significant"] = (
            (out["q_value"] < 0.10) & (out["n"] >= 30)
            & (np.sign(out["first_half_bps"]) == np.sign(out["second_half_bps"]))
            & (np.sign(out["first_half_bps"]) == np.sign(out["mean_excess_bps"]))
        )
    return out
