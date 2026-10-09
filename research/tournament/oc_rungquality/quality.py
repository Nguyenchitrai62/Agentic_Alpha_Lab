"""oc_rungquality: dip-rung quality filter (IDEAS5 #9).

Frozen PLAN.md helpers (no data access in pure functions; unit-tested).
Copies labelled below are verbatim from research/tournament/oc_ladderfill/analyze_ladderfill.py.

Cells: 25 = 5 majors x 5 R2 depths. F1 skips cells with trailing stop-given-fill
rate > p80; F2 = F1 + cells with trailing fill rate < p20. Trailing window per
anchor A: T in [A - 97d, A - 7d) AND exit_t < A - 7d. min_n = 10 (frozen).
"""
from __future__ import annotations

from collections import deque

import numpy as np
import pandas as pd

MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
DEPTHS = (2.5, 3.0, 3.5, 4.0, 5.0)
ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
MIN_N = 10  # frozen: cells with fewer trailing fills get stop_rate NaN (never F1-skipped)
EXIT_STOP = "rung_sl"
N_BAR_WINDOW = 4 * 540  # 90d x 6 bars/day x 4 shifts; exact (window length is a multiple of 240 min)


# ---- COPIED verbatim from oc_ladderfill/analyze_ladderfill.py (labelled copy) ----
def fill_minute(t: pd.Timestamp, shift: int) -> int:
    # Shift-s replica runs on the 4h grid offset by s hours: bars open at
    # hours = s (mod 4). Verified: this gives exactly 16..238 on every shift
    # (unshifted grid gives 0..239 with outsiders on s=1..3).
    mins = (t - t.floor("D")).total_seconds() / 60.0
    return int((mins - shift * 60) % 240)


# ---- COPIED verbatim from oc_ladderfill/analyze_ladderfill.py::pair_shift (labelled copy) ----
def pair_shift(ev: pd.DataFrame, shift: int):
    """FIFO per symbol. Returns (rungs list, unpaired_exits, left_open)."""
    pend: dict[str, deque] = {}
    out, unpaired = [], 0
    for r in ev.itertuples():
        if r.kind == "rung_fill":
            pend.setdefault(r.symbol, deque()).append(r)
        elif r.kind in ("rung_sl", "rung_tp", "rung_timeout"):
            q = pend.get(r.symbol)
            if q:
                f0 = q.popleft()
                out.append(dict(
                    shift=shift, symbol=r.symbol, depth=float(f0.rung),
                    weight=float(f0.weight), fill_t=pd.Timestamp(f0.t),
                    exit_t=pd.Timestamp(r.t), exit=r.kind,
                    ret=float(r.ret),
                ))
            else:
                unpaired += 1
    left = sum(len(q) for q in pend.values())
    return out, unpaired, left


# ---- frozen quality-stat helpers (pure, unit-tested) ----
def trailing_stats(pairs: pd.DataFrame, anchor: str) -> pd.DataFrame:
    """Per-cell trailing stats in W(A) = [A-97d, A-7d), exit_t < A-7d.

    pairs cols: symbol, depth, fill_t, exit_t, exit (all tz-aware UTC).
    Returns DataFrame with cols sym, depth, n_fill, n_stop, stop_rate, fill_rate.
    stop_rate NaN when n_fill < MIN_N. fill_rate = n_fill / N_BAR_WINDOW.
    """
    a = pd.Timestamp(anchor, tz="UTC")
    lo, hi = a - pd.Timedelta(days=97), a - pd.Timedelta(days=7)
    assert "T" in pairs.columns, "call with_T() first"
    df = pairs[(pd.to_datetime(pairs["T"], utc=True) >= lo)
               & (pd.to_datetime(pairs["T"], utc=True) < hi)
               & (pd.to_datetime(pairs["exit_t"], utc=True) < hi)].copy()
    rows = []
    for sym in MAJORS:
        for depth in DEPTHS:
            g = df[(df["symbol"] == sym) & (df["depth"] == depth)]
            n = int(len(g))
            ns = int((g["exit"] == EXIT_STOP).sum()) if n else 0
            sr = float(ns / n) if n >= MIN_N else float("nan")
            rows.append({"sym": sym, "depth": float(depth), "n_fill": n,
                         "n_stop": ns, "stop_rate": sr,
                         "fill_rate": float(n / N_BAR_WINDOW)})
    return pd.DataFrame(rows)


def skip_sets(stats: pd.DataFrame) -> dict:
    """Frozen F1/F2 skip sets from per-anchor stats.

    p80 over finite stop_rates; p20 over all 25 fill_rates. Strict inequalities
    (ties keep). Returns dict with p80, p20, f1 (list of [sym, depth]), f2.
    Empty stats (all n_fill == 0, e.g. 2021 anchor) -> empty skip sets.
    """
    sr = pd.to_numeric(stats["stop_rate"], errors="coerce").dropna().to_numpy(float)
    fr = pd.to_numeric(stats["fill_rate"], errors="coerce").to_numpy(float)
    p80 = float(np.quantile(sr, 0.80)) if len(sr) else float("nan")
    p20 = float(np.quantile(fr, 0.20)) if len(fr) else float("nan")
    f1, f1keys = [], set()
    if np.isfinite(p80):
        for r in stats.itertuples():
            if np.isfinite(float(r.stop_rate)) and float(r.stop_rate) > p80:
                f1.append([str(r.sym), float(r.depth)])
                f1keys.add((str(r.sym), float(r.depth)))
    f2 = [c for c in f1]
    f2keys = set(f1keys)
    if np.isfinite(p20):
        for r in stats.itertuples():
            if float(r.fill_rate) < p20 and (str(r.sym), float(r.depth)) not in f2keys:
                f2.append([str(r.sym), float(r.depth)])
                f2keys.add((str(r.sym), float(r.depth)))
    return {"p80": p80, "p20": p20, "f1": f1, "f2": f2}


def with_T(pairs: pd.DataFrame) -> pd.DataFrame:
    """Attach holding-bar open T = fill_t - fill_minute(fill_t, shift)."""
    df = pairs.copy()
    df["fill_t"] = pd.to_datetime(df["fill_t"], utc=True)
    df["T"] = [pd.Timestamp(t) - pd.Timedelta(minutes=fill_minute(pd.Timestamp(t), int(s)))
               for t, s in zip(df["fill_t"], df["shift"])]
    df["T"] = pd.to_datetime(df["T"], utc=True)
    return df
