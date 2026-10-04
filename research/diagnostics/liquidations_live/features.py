"""Causal readers and 1-minute / 4h features for the live liquidation recordings (backend/liquidations.py).

Research-only helpers, no strategy uses them yet. Data: data/raw/liquidations_live/{venue}/{SYMBOL}/YYYY-MM-DD.parquet
(columns venue, symbol, side, raw_side, price, qty, notional_usd, event_time, recv_time; side "long" = a long position
was liquidated (forced sell), "short" = a short was liquidated (forced buy)) and the connected-interval files in
data/raw/liquidations_live/_coverage/{venue}/YYYY-MM-DD.parquet.

Causality (AGENTS.md rule 1): an event is usable at time t only if BOTH event_time < t and recv_time < t (the live
pipeline would only have seen it on receipt). A 1-minute bucket [m, m + 60 s) becomes available at
available_ms = max(m + 60 s, last recv_time in the bucket + 1); as-of joins include a bucket only if available_ms <= t.
Binance pushes at most one liquidation per symbol per second (a lower bound of the true flow); Bybit pushes all.
Coverage: minutes when the venue's liquidation stream was not connected are unknown, not zero - use ``covered``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
LIQ_DIR = ROOT / "data/raw/liquidations_live"
MIN_MS = 60_000
DAY_MS = 86_400_000
H4_MS = 4 * 3_600_000
EVENT_COLUMNS = ["venue", "symbol", "side", "raw_side", "price", "qty", "notional_usd", "event_time", "recv_time"]


def _days(start_ms: int | None, end_ms: int | None) -> set[str] | None:
    if start_ms is None or end_ms is None:
        return None
    d0, d1 = int(start_ms) // DAY_MS, (int(end_ms) - 1) // DAY_MS
    return {pd.Timestamp(d * DAY_MS, unit="ms").strftime("%Y-%m-%d") for d in range(d0, d1 + 1)}


def load_events(root: Path = LIQ_DIR, venues: Iterable[str] | None = None, symbols: Iterable[str] | None = None,
                start_ms: int | None = None, end_ms: int | None = None) -> pd.DataFrame:
    """All recorded liquidation events with start_ms <= event_time < end_ms (both optional), sorted by event_time."""
    root = Path(root)
    days = _days(start_ms, end_ms)
    vs = list(venues) if venues else sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith("_")) if root.exists() else []
    parts = []
    for v in vs:
        vdir = root / v
        if not vdir.exists():
            continue
        syms = [s.upper() for s in symbols] if symbols else sorted(p.name for p in vdir.iterdir() if p.is_dir())
        for s in syms:
            for f in sorted((vdir / s).glob("*.parquet")) if (vdir / s).exists() else []:
                if f.name.startswith(".") or ".corrupt-" in f.name or (days is not None and f.stem not in days):
                    continue
                parts.append(pd.read_parquet(f))
    if not parts:
        return pd.DataFrame(columns=EVENT_COLUMNS)
    df = pd.concat(parts, ignore_index=True)
    if start_ms is not None:
        df = df[df["event_time"] >= int(start_ms)]
    if end_ms is not None:
        df = df[df["event_time"] < int(end_ms)]
    return df.sort_values(["event_time", "venue", "symbol"], kind="mergesort").reset_index(drop=True)


def events_before(events: pd.DataFrame, t_ms: int) -> pd.DataFrame:
    """Strictly causal slice: events both happened and were received before ``t_ms``."""
    m = (events["event_time"] < int(t_ms)) & (events["recv_time"] < int(t_ms))
    return events[m]


def load_coverage(root: Path = LIQ_DIR, venues: Iterable[str] | None = None) -> pd.DataFrame:
    """Merged connected intervals per venue: columns venue, start_ms, end_ms (half-open)."""
    cdir = Path(root) / "_coverage"
    vs = list(venues) if venues else (sorted(p.name for p in cdir.iterdir() if p.is_dir()) if cdir.exists() else [])
    parts = [pd.read_parquet(f) for v in vs if (cdir / v).exists() for f in sorted((cdir / v).glob("*.parquet"))
             if not f.name.startswith(".") and ".corrupt-" not in f.name]
    if not parts:
        return pd.DataFrame(columns=["venue", "start_ms", "end_ms"])
    return merge_intervals(pd.concat(parts, ignore_index=True))


def merge_intervals(cov: pd.DataFrame) -> pd.DataFrame:
    out = []
    for v, g in cov.sort_values(["venue", "start_ms"]).groupby("venue", sort=True):
        cur_s = cur_e = None
        for s, e in zip(g["start_ms"].astype("int64"), g["end_ms"].astype("int64")):
            if cur_e is not None and s <= cur_e:
                cur_e = max(cur_e, e)
            else:
                if cur_s is not None:
                    out.append((v, cur_s, cur_e))
                cur_s, cur_e = s, e
        if cur_s is not None:
            out.append((v, cur_s, cur_e))
    return pd.DataFrame(out, columns=["venue", "start_ms", "end_ms"])


def covered_minutes(coverage: pd.DataFrame, venue: str) -> set[int]:
    """Minute starts (ms) whose whole minute lies inside a connected interval of ``venue``."""
    mins: set[int] = set()
    for s, e in coverage.loc[coverage["venue"] == venue, ["start_ms", "end_ms"]].itertuples(index=False):
        first = -(-int(s) // MIN_MS) * MIN_MS
        last = (int(e) // MIN_MS) * MIN_MS  # exclusive
        mins.update(range(first, last, MIN_MS))
    return mins


def minute_buckets(events: pd.DataFrame, by_venue: bool = False) -> pd.DataFrame:
    """Per symbol (and venue if ``by_venue``) and 1-minute bucket of event_time: long/short liquidation notional and
    counts, plus ``available_ms`` (when the whole bucket is knowable). Minutes without events are absent (see coverage)."""
    keys = (["venue"] if by_venue else []) + ["symbol", "minute_ms"]
    cols = keys + ["long_liq_notional", "short_liq_notional", "long_liq_count", "short_liq_count", "available_ms"]
    if events.empty:
        return pd.DataFrame(columns=cols)
    e = events.copy()
    e["minute_ms"] = (e["event_time"].astype("int64") // MIN_MS) * MIN_MS
    is_long = e["side"].eq("long")
    e["long_liq_notional"] = np.where(is_long, e["notional_usd"], 0.0)
    e["short_liq_notional"] = np.where(~is_long, e["notional_usd"], 0.0)
    e["long_liq_count"] = is_long.astype(int)
    e["short_liq_count"] = (~is_long).astype(int)
    g = e.groupby(keys, sort=True).agg(long_liq_notional=("long_liq_notional", "sum"),
                                       short_liq_notional=("short_liq_notional", "sum"),
                                       long_liq_count=("long_liq_count", "sum"), short_liq_count=("short_liq_count", "sum"),
                                       max_recv=("recv_time", "max")).reset_index()
    g["available_ms"] = np.maximum(g["minute_ms"] + MIN_MS, g["max_recv"].astype("int64") + 1)
    return g.drop(columns="max_recv")[cols]


def asof_window(buckets: pd.DataFrame, times_ms: Iterable[int], window_minutes: int, symbols: Iterable[str] | None = None,
                coverage: pd.DataFrame | None = None, venues: Iterable[str] | None = None) -> pd.DataFrame:
    """For every symbol and query time t: sums over buckets with t - window <= minute_ms and available_ms <= t
    (strictly before t). With ``coverage``, ``coverage_frac`` = share of the window's whole minutes ending by t during
    which every venue in ``venues`` was connected (NaN-safe gating is left to the caller)."""
    times = np.asarray(sorted(int(t) for t in times_ms), dtype="int64")
    w = int(window_minutes) * MIN_MS
    syms = list(symbols) if symbols is not None else sorted(buckets["symbol"].unique()) if len(buckets) else []
    cov_sets = None
    if coverage is not None:
        vs = list(venues) if venues else sorted(coverage["venue"].unique())
        sets = [covered_minutes(coverage, v) for v in vs]
        cov_sets = set.intersection(*sets) if sets else set()
    rows = []
    for s in syms:
        b = buckets[buckets["symbol"] == s].sort_values("minute_ms") if len(buckets) else buckets
        ms = b["minute_ms"].to_numpy("int64") if len(b) else np.empty(0, "int64")
        av = b["available_ms"].to_numpy("int64") if len(b) else np.empty(0, "int64")
        ln = b["long_liq_notional"].to_numpy(float) if len(b) else np.empty(0)
        sn = b["short_liq_notional"].to_numpy(float) if len(b) else np.empty(0)
        lc = b["long_liq_count"].to_numpy(float) if len(b) else np.empty(0)
        sc = b["short_liq_count"].to_numpy(float) if len(b) else np.empty(0)
        for t in times:
            i0, i1 = np.searchsorted(ms, t - w, "left"), np.searchsorted(ms, t, "left")
            m = av[i0:i1] <= t
            L, S = float(ln[i0:i1][m].sum()), float(sn[i0:i1][m].sum())
            row = {"symbol": s, "time_ms": int(t), f"long_liq_{window_minutes}m": L, f"short_liq_{window_minutes}m": S,
                   f"long_cnt_{window_minutes}m": float(lc[i0:i1][m].sum()), f"short_cnt_{window_minutes}m": float(sc[i0:i1][m].sum()),
                   f"liq_imbalance_{window_minutes}m": (L - S) / (L + S) if L + S > 0 else 0.0}
            if cov_sets is not None:
                first = -(-(t - w) // MIN_MS) * MIN_MS
                n_min = max(1, (t - first) // MIN_MS)
                row[f"coverage_frac_{window_minutes}m"] = sum(1 for k in range(first, t - MIN_MS + 1, MIN_MS) if k in cov_sets) / n_min
            rows.append(row)
    return pd.DataFrame(rows)


def features_4h(bar_close_ms: Iterable[int], root: Path = LIQ_DIR, symbols: Iterable[str] | None = None,
                venues: Iterable[str] | None = None, windows: tuple[int, ...] = (60, 240)) -> pd.DataFrame:
    """4h-close features: long/short liquidation notional, counts and imbalance over each window, strictly before each
    bar close, pooled across ``venues``, with coverage fractions. One row per (symbol, time_ms)."""
    closes = sorted(int(t) for t in bar_close_ms)
    if not closes:
        return pd.DataFrame()
    lo = closes[0] - max(windows) * MIN_MS
    ev = load_events(root, venues, symbols, lo, closes[-1])
    b = minute_buckets(ev)
    cov = load_coverage(root, venues)
    syms = [s.upper() for s in symbols] if symbols else sorted(ev["symbol"].unique())
    out = None
    for w in windows:
        f = asof_window(b, closes, w, syms, coverage=cov, venues=venues)
        out = f if out is None else out.merge(f, on=["symbol", "time_ms"], how="outer")
    return out.sort_values(["time_ms", "symbol"]).reset_index(drop=True) if out is not None else pd.DataFrame()
