"""Order-book depth features for dip-limit fills (tag bookdepth). Fixed definitions (2026-10-04, before results).

Source table: data/raw/bookdepth_20261004/{SYM}_bookdepth_1m.parquet (last exchange snapshot per minute;
ts = snapshot publish time, UTC; bid/ask notionals at +-1/2/5 % from mid).

Features for a decision time T (a dip-limit fill minute t_fill, or a 4h bar close):
  imb_1      = (bid_n1 - ask_n1) / (bid_n1 + ask_n1)          at now
  imb_2      = (bid_n2 - ask_n2) / (bid_n2 + ask_n2)          at now
  depth_rel_7d = (bid_n1 + ask_n1)(now) / median(bid_n1 + ask_n1 over minutes in [T-7d, T))
  chg_bid_15 = bid_n1(now) / bid_n1(lag15) - 1
  chg_bid_60 = bid_n1(now) / bid_n1(lag60) - 1

As-of rule (strict, asserted): now   = last snapshot with ts < T (strictly before the decision time);
lag15/60 = last snapshot with ts <= T - 15/60 min. depth_rel_7d uses only minutes < T (minute floor
of T excluded... included only if its snapshot ts < T; implemented on ts). Minimum 1000 minutes in
the 7-day window, else NaN. No forward fill across T. Lags missing (start of history) -> NaN.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "bookdepth_20261004"
FEATURES = ("bd_imb_1", "bd_imb_2", "bd_depth_rel_7d", "bd_chg_bid_15", "bd_chg_bid_60")
LAGS = {"bd_chg_bid_15": pd.Timedelta(minutes=15), "bd_chg_bid_60": pd.Timedelta(minutes=60)}
WINDOW_7D = pd.Timedelta(days=7)
MIN_WINDOW_MINUTES = 1000


def load_depth(sym: str) -> pd.DataFrame:
    d = pd.read_parquet(DATA_DIR / f"{sym}_bookdepth_1m.parquet").sort_values("ts").reset_index(drop=True)
    d["total_1"] = d["bid_n1"] + d["ask_n1"]
    return d


def attach_features(decisions: pd.DataFrame, depth: dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
    """Attach causal depth features to a decisions frame with columns [sym, T].

    Every output row uses only snapshots with ts strictly before its T (asserted).
    NaN where history is missing (before 2023-01-01, first 60 min, thin 7d window).
    """
    if list(decisions.columns) != ["sym", "T"]:
        raise ValueError("decisions must have columns [sym, T]")
    if depth is None:
        depth = {s: load_depth(s) for s in decisions["sym"].unique()}
    out = []
    for sym, grp in decisions.groupby("sym", sort=False):
        d = depth[sym].sort_values("ts").reset_index(drop=True)
        ts = d["ts"].to_numpy(dtype="datetime64[ns]")
        T = pd.to_datetime(grp["T"], utc=True).to_numpy(dtype="datetime64[ns]")
        # now: last snapshot with ts < T (strict) -> searchsorted left, step back
        i_now = np.searchsorted(ts, T, side="left") - 1
        ok = i_now >= 0
        now_ts = np.full(len(grp), np.datetime64("NaT"), dtype="datetime64[ns]")
        now_ts[ok] = ts[np.clip(i_now[ok], 0, len(ts) - 1)]
        if (pd.to_datetime(now_ts[ok]) >= pd.to_datetime(T[ok])).any():
            raise AssertionError("as-of violation: snapshot ts not strictly before T")
        res = pd.DataFrame({c: np.nan for c in FEATURES}, index=grp.index, dtype=float)
        if not ok.any():
            out.append(res)
            continue
        bid1 = d["bid_n1"].to_numpy(float)
        ask1 = d["ask_n1"].to_numpy(float)
        bid2 = d["bid_n2"].to_numpy(float)
        ask2 = d["ask_n2"].to_numpy(float)
        tot = d["total_1"].to_numpy(float)
        mins = d["minute"].to_numpy(dtype="datetime64[ns]")
        idx = np.where(ok)[0]
        i0 = np.clip(i_now[idx], 0, len(d) - 1)
        res.loc[grp.index[idx], "bd_imb_1"] = (bid1[i0] - ask1[i0]) / (bid1[i0] + ask1[i0])
        res.loc[grp.index[idx], "bd_imb_2"] = (bid2[i0] - ask2[i0]) / (bid2[i0] + ask2[i0])
        for col, lag in LAGS.items():
            i_lag = np.searchsorted(ts, T[idx] - np.timedelta64(lag.value, "ns"), side="right") - 1
            has = i_lag >= 0
            v = np.full(len(idx), np.nan)
            v[has] = bid1[np.clip(i_lag[has], 0, len(d) - 1)]
            with np.errstate(divide="ignore", invalid="ignore"):
                res.loc[grp.index[idx], col] = bid1[i0] / v - 1.0
        # trailing 7-day median of 1-min totals, minutes strictly before T
        lo = T[idx] - np.timedelta64(WINDOW_7D.value, "ns")
        j_lo = np.searchsorted(mins, lo, side="left")
        j_hi = np.searchsorted(mins, T[idx], side="left")
        med = np.full(len(idx), np.nan)
        for k in range(len(idx)):
            w = tot[j_lo[k]:max(j_hi[k], j_lo[k])]
            if len(w) >= MIN_WINDOW_MINUTES:
                med[k] = np.median(w)
        with np.errstate(divide="ignore", invalid="ignore"):
            res.loc[grp.index[idx], "bd_depth_rel_7d"] = tot[i0] / med
        out.append(res)
    feats = pd.concat(out).loc[decisions.index]
    return feats
