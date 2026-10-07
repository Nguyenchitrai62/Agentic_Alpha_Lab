"""oc_kellydip: analytical Kelly/DD sizing of the dip sleeve (see PLAN.md, pre-registered).

Universe: research/tournament/ext/fills_U_ext.parquet, majors R2 rungs (y1.0),
5 anchor years keyed by T. Timestamp-only n (same T, |dt|<=15min, other majors).
Per year x weighting (flat / 1/(1+n)): Kelly f* via bisection on G', daily-sum
maxDD fractions for 15%/20%, deployed f_dep=1.7 comparison. LIGHT: one process,
fills file only, no 1m data.

Usage: .venv/Scripts/python.exe research/tournament/oc_kellydip/compute_kelly.py
Writes results.json in this folder.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FILLS = ROOT / "research/tournament/ext/fills_U_ext.parquet"
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in (
    "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
DEV_END = pd.Timestamp("2026-09-24", tz="UTC")
F_DEP = 1.7
FMAX_CAP = 20.0


def kelly_star(z: np.ndarray):
    """Growth-optimal f>=0 for G(f)=mean(log(1+f*z)). Returns (fstar, capped)."""
    z = np.asarray(z, float)
    assert np.isfinite(z).all() and len(z) > 0

    def gp(f):
        return float(np.mean(z / (1.0 + f * z)))

    if gp(0.0) <= 0:
        return 0.0, False
    zmin = float(z.min())
    if zmin >= 0:
        fmax = FMAX_CAP
    else:
        fmax = min(0.999 / (-zmin), FMAX_CAP)
    if gp(fmax) >= 0:
        return fmax, True  # optimum at/above cap
    lo, hi = 0.0, fmax
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if gp(mid) >= 0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi), False


def growth(z: np.ndarray, f: float) -> float:
    z = np.asarray(z, float)
    v = 1.0 + f * z
    if (v <= 0).any():
        return float("-inf")
    return float(np.mean(np.log(v)))


def count_n(tfill: np.ndarray, sym: np.ndarray, T: np.ndarray) -> np.ndarray:
    """Distinct OTHER symbols with same T and |t_fill diff| <= 15 min (0..4)."""
    n = np.zeros(len(tfill), int)
    pos = {t: ii for t, ii in pd.DataFrame({"T": T}).groupby("T", sort=False).groups.items()}
    for ii in pos.values():
        ii = np.asarray(list(ii))
        if len(ii) == 1:
            continue
        tf, sm = tfill[ii], sym[ii]
        dt = np.abs((tf[:, None] - tf[None, :]).astype("timedelta64[s]").astype(float)) / 60.0
        near = dt <= 15.0 + 1e-9
        for a in range(len(ii)):
            n[ii[a]] = len({sm[b] for b in range(len(ii)) if sm[b] != sm[a] and near[a, b]})
    return n


def dd_stats(daily: pd.Series):
    """daily: sums per day sorted chronologically. Returns (maxDD1<=0)."""
    c = np.asarray(daily.to_numpy(), float).cumsum()
    peak = np.maximum.accumulate(c)
    return float(np.min(c - peak))


def main():
    d = pd.read_parquet(FILLS)
    d = d[d.t_fill < DEV_END].copy()
    d["T"] = d.t_fill - pd.to_timedelta(d.f, unit="min")
    uni = d[d.sym.isin(MAJORS) & d.x1.isin(R2)].copy()
    uni = uni.sort_values("t_fill").reset_index(drop=True)
    # year assignment by T
    uni["year"] = -1
    for yi, a0 in enumerate(ANCHORS):
        m = (uni["T"] >= a0) & (uni["T"] < a0 + pd.Timedelta(days=365))
        uni.loc[m, "year"] = yi
    uni = uni[uni.year >= 0].copy().reset_index(drop=True)

    # n: distinct other coins, same T, |dt|<=15min (within the majors-R2 universe)
    uni["n"] = count_n(uni.t_fill.to_numpy(), uni.sym.to_numpy(), uni["T"].to_numpy())
    assert uni["n"].between(0, 4).all()
    uni["w_shrunk"] = 1.0 / (1.0 + uni["n"].to_numpy())

    n_hist_share, n_hist_counts, counts = {}, {}, []
    for yi, a0 in enumerate(ANCHORS):
        sub = uni[uni.year == yi]
        counts.append(int(len(sub)))
        vc = sub["n"].value_counts().reindex(range(5), fill_value=0)
        n_hist_counts[str(a0.date())] = {str(k): int(vc[k]) for k in range(5)}
        n_hist_share[str(a0.date())] = {str(k): round(float(vc[k] / max(len(sub), 1)), 4) for k in range(5)}
    vc = uni["n"].value_counts().reindex(range(5), fill_value=0)
    n_hist_counts["overall"] = {str(k): int(vc[k]) for k in range(5)}
    n_hist_share["overall"] = {str(k): round(float(vc[k] / max(len(uni), 1)), 4) for k in range(5)}
    n_hist_share["counts_per_year"] = {str(a.date()): counts[i] for i, a in enumerate(ANCHORS)}

    years = []
    for yi, a0 in enumerate(ANCHORS):
        sub = uni[uni.year == yi].sort_values("t_fill")
        y = sub["y1.0"].to_numpy(float)
        w = sub["w_shrunk"].to_numpy(float)
        assert np.isfinite(y).all() and (y != 0).any()
        row = {"year": str(a0.date()), "n_rungs": int(len(sub)),
               "mean_y1": round(float(y.mean()), 6),
               "winrate_y1": round(float((y > 0).mean()), 4)}
        day = sub["T"].dt.floor("D").to_numpy()
        for wname, z in (("flat", y), ("shrunk", w * y)):
            fs, capped = kelly_star(z)
            g_star = growth(z, fs)
            g1 = growth(z, 1.0)
            gdep = growth(z, F_DEP)
            min_dep = float(np.min(1.0 + F_DEP * z))
            ds = pd.Series(z).groupby(day).sum().sort_index()
            mdd1 = dd_stats(ds)
            f15 = (0.15 / (-mdd1)) if mdd1 < 0 else None
            f20 = (0.20 / (-mdd1)) if mdd1 < 0 else None
            dd_dep = F_DEP * mdd1
            row[wname] = {
                "f_star": round(float(fs), 4), "capped_at_20": bool(capped),
                "G_star": round(float(g_star), 6), "G_1": round(float(g1), 6),
                "G_dep": round(float(gdep), 6) if np.isfinite(gdep) else None,
                "min_1_plus_dep_z": round(float(min_dep), 6),
                "worst_day_1": round(float(ds.min()), 6),
                "maxDD_1": round(float(mdd1), 6),
                "f_DD15": round(float(f15), 4) if f15 is not None else None,
                "f_DD20": round(float(f20), 4) if f20 is not None else None,
                "DD_dep": round(float(dd_dep), 6),
                "dep_over_fstar": round(float(F_DEP / fs), 4) if fs > 0 else None,
                "dep_over_fDD15": round(float(F_DEP / f15), 4) if f15 else None,
                "dep_over_fDD20": round(float(F_DEP / f20), 4) if f20 else None,
            }
        years.append(row)
        print(json.dumps(row), flush=True)

    res = {
        "universe": {"file": "research/tournament/ext/fills_U_ext.parquet",
                     "majors_R2_5y": int(len(uni)), "per_year": counts,
                     "anchors": [str(a.date()) for a in ANCHORS],
                     "outcome": "y1.0", "unit": "R2 base per-rung notional (flat w=1)",
                     "f_dep": F_DEP,
                     "n_def": "distinct other majors coins with >=1 R2 fill, same T, |t_fill diff|<=15min"},
        "n_hist_share": n_hist_share, "n_hist_counts": n_hist_counts,
        "years": years,
        "notes": ("Kelly f* maximises mean(log(1+f*z)) in t_fill order per year; "
                  "DD from daily sums of z by T.floor(D), maxDD(f)=f*maxDD1; "
                  "descriptive only, no rule."),
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print("wrote results.json", len(uni), "rungs", flush=True)


if __name__ == "__main__":
    main()
