"""oc_weekend: weekend dip tilt (IDEAS.md idea #18).

Frozen PLAN.md definitions. LIGHT: fills only, one process, < 1 GB.
Causality: weekend flag is a pure function of the holding-bar open T
(Sat 00:00 <= T < Mon 00:00 UTC), known when the bid is placed.

Fixed tilt: m(T) = 1.25 weekend else 0.90; size_new = size_dep * m(T);
scored with harness5 equal-exposure renormalisation per year.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
import sys
sys.path.insert(0, str(ROOT / "research" / "tournament" / "ext"))
import harness5 as H5

OUT = ROOT / "research" / "tournament" / "oc_weekend"
MAJORS = H5.MAJORS
R2 = H5.R2
ANCHORS = H5.ANCHORS
M_WKND = 1.25
M_WKDAY = 0.90


def is_weekend(T: pd.DatetimeIndex | pd.Series) -> np.ndarray:
    """Weekend iff Sat 00:00 <= T < Mon 00:00 UTC (dayofweek 5/6, Monday=0)."""
    t = pd.DatetimeIndex(pd.to_datetime(T, utc=True))
    return (t.dayofweek.to_numpy() == 5) | (t.dayofweek.to_numpy() == 6)


def assign_mult(T: pd.DatetimeIndex | pd.Series) -> np.ndarray:
    """Fixed bar multiplier: 1.25 weekend else 0.90."""
    w = is_weekend(T)
    return np.where(w, M_WKND, M_WKDAY).astype(float)


def maxdd_daily(daily: pd.Series) -> float:
    """Max drawdown of a cumulative daily-sum path (P_0 = 0 included)."""
    d = np.asarray(daily.sort_index().to_numpy(), dtype=float)
    if d.size == 0:
        return float("nan")
    p = np.concatenate([[0.0], np.cumsum(d)])
    peak = np.maximum.accumulate(p)
    return float(np.max(peak - p))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    d = H5.load()
    d["T"] = pd.to_datetime(d["T"], utc=True)
    assert bool((d["T"] < H5.DEV_END).all()), "fill T beyond 2026-09-24"
    is_r2 = d["sym"].isin(MAJORS) & d["k"].isin(R2) & d["size_dep"].notna()
    dr = d.loc[is_r2].copy().reset_index(drop=True)
    dr["wknd"] = is_weekend(dr["T"])
    dr["mult"] = assign_mult(dr["T"])

    yv = dr["y_dep"].to_numpy(float)
    wk = dr["wknd"].to_numpy(bool)
    sd_all = dr["size_dep"].to_numpy(float)
    mult_all = dr["mult"].to_numpy(float)
    anchors = list(ANCHORS)
    year_mask = [((dr["T"] >= a0) & (dr["T"] < a0 + pd.Timedelta(days=365))).to_numpy()
                 for a0 in anchors]

    # --- tilted vs base with harness5 equal-exposure renorm ---
    size_seq = np.full(len(d), np.nan)
    # map dr rows back to d rows for harness scoring
    d_idx = d.index[is_r2.to_numpy()].to_numpy()
    size_seq[d_idx] = sd_all * mult_all
    scored = H5.score(d, size_seq, name="weekend_tilt")

    years_out = []
    for k, a0 in enumerate(anchors):
        te = year_mask[k]
        y = yv[te]
        w = wk[te]
        sd = sd_all[te]
        sn_raw = sd * mult_all[te]
        # harness renorm inside the year (same as H5.score)
        sn = sn_raw * sd.mean() / max(sn_raw.mean(), 1e-12)
        n_wknd, n_wkday = int(w.sum()), int((~w).sum())
        mw = float(y[w].mean()) if n_wknd else float("nan")
        md = float(y[~w].mean()) if n_wkday else float("nan")
        spread = float(mw - md) if (n_wknd and n_wkday) else float("nan")
        ww = float((y[w] > 0).mean()) if n_wknd else float("nan")
        wd = float((y[~w] > 0).mean()) if n_wkday else float("nan")
        yr = scored["years"][k]
        # daily paths (renormalised) for maxDD
        tdays = dr["T"].to_numpy()[te]
        day = pd.to_datetime(tdays, utc=True).floor("D")
        s_dep_s = pd.Series(sd * y).groupby(day).sum().sort_index()
        s_new_s = pd.Series(sn * y).groupby(day).sum().sort_index()
        raw_dep = float((sd * y).sum())
        raw_new = float((sn_raw * y).sum())
        # per-coin spread split (descriptive)
        coin_split = {}
        for c in MAJORS:
            cm = (dr["sym"].to_numpy()[te] == c)
            if int(cm.sum()):
                yw, ww_ = y[cm & w], y[cm & ~w]
                coin_split[c] = {
                    "n_wknd": int((cm & w).sum()),
                    "n_wkday": int((cm & ~w).sum()),
                    "spread": round(float(yw.mean() - ww_.mean()), 6)
                    if (len(yw) and len(ww_)) else None,
                }
        years_out.append({
            "anchor": str(a0.date()),
            "n": int(te.sum()),
            "n_wknd": n_wknd, "n_wkday": n_wkday,
            "wknd_share": round(n_wknd / max(int(te.sum()), 1), 4),
            "mean_wknd": round(mw, 6), "mean_wkday": round(md, 6),
            "spread": round(spread, 6),
            "spread_bps": round(spread * 1e4, 2),
            "win_wknd": round(ww, 4), "win_wkday": round(wd, 4),
            "spread_pass": bool(np.isfinite(spread) and spread > 0),
            "S_dep": yr["S_dep"], "S_new": yr["S_new"],
            "gain": yr["gain"],
            "worst_day_dep": yr["worst_day_dep"],
            "worst_day_new": yr["worst_day_new"],
            "tail_pass": bool(yr["worst_day_new"] >= yr["worst_day_dep"]),
            "maxDD_dep": round(maxdd_daily(s_dep_s), 4),
            "maxDD_new": round(maxdd_daily(s_new_s), 4),
            "S_raw_dep": round(raw_dep, 4), "S_raw_new": round(raw_new, 4),
            "retention_raw": round(raw_new / raw_dep, 4) if raw_dep > 0 else None,
            "per_coin_spread": coin_split,
        })

    # --- LOYO: pooled spread of the other 4 years ---
    loyo = []
    for hh in range(5):
        tr = np.zeros(len(dr), bool)
        for k in range(5):
            if k != hh:
                tr |= year_mask[k]
        yw, yd = yv[tr & wk], yv[tr & ~wk]
        sp = float(yw.mean() - yd.mean()) if (len(yw) and len(yd)) else float("nan")
        loyo.append({
            "heldout": str(anchors[hh].date()),
            "n_wknd_train": int((tr & wk).sum()),
            "n_wkday_train": int((tr & ~wk).sum()),
            "spread_pool": round(sp, 6) if np.isfinite(sp) else None,
            "spread_pool_bps": round(sp * 1e4, 2) if np.isfinite(sp) else None,
            "pass": bool(np.isfinite(sp) and sp > 0),
        })

    n_spread = sum(1 for y in years_out if y["spread_pass"])
    n_loyo = sum(1 for r in loyo if r["pass"])
    n_tail = sum(1 for y in years_out if y["tail_pass"])
    promising = bool(n_spread >= 4 and n_loyo >= 4 and n_tail >= 4)
    res = {
        "meta": {
            "fills": str(H5.FILLS),
            "universe": "majors x R2(2.5,3,3.5,4,5) with size_dep, outcome y_dep",
            "variant": "single fixed tilt m={1.25 weekend, 0.90 weekday}, harness5 renorm per year",
            "weekend": "Sat 00:00 <= T < Mon 00:00 UTC (dayofweek 5/6); T=t_fill-f, 4h-aligned",
            "T_min": str(dr["T"].min()), "T_max": str(dr["T"].max()),
            "unit": "native size*y_dep units; spread also in bps x1e4",
        },
        "years": years_out,
        "loyo": loyo,
        "decision": {
            "spread_sequential": f"{n_spread}/5",
            "loyo_spread": f"{n_loyo}/5",
            "tail_not_worse": f"{n_tail}/5",
            "promising": promising,
        },
    }
    (OUT / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["decision"], indent=1))
    for y in years_out:
        print(y["anchor"], "n", y["n"], "shr", y["wknd_share"],
              "spread_bps", y["spread_bps"], "pass", y["spread_pass"],
              "gain", y["gain"], "W", y["worst_day_dep"], "->",
              y["worst_day_new"], "tail", y["tail_pass"],
              "maxDD", y["maxDD_dep"], "->", y["maxDD_new"])
    for r in loyo:
        print("LOYO", r["heldout"], "pool_bps", r["spread_pool_bps"], "pass", r["pass"])


if __name__ == "__main__":
    main()
