"""oc_coinwf: walk-forward per-coin dip weights (idea #12, PLAN.md frozen first).

Universe: majors x R2 depths, outcome y1.0. Per anchor, score_c =
mean(y1.0)/std(y1.0, ddof=1) over history t_fill in (2020-08-01, anchor-7d);
w_raw = clip(score/mean_score, 0.5, 1.5); w = w_raw/mean(w_raw).
Metrics per year keyed by t_fill in [anchor, anchor+365d).
LIGHT: pandas only, one process.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FILLS = ROOT / "research" / "tournament" / "ext" / "fills_U_ext.parquet"
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in (
    "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
EMBARGO = pd.Timedelta(days=7)
HIST_START = pd.Timestamp("2020-08-01", tz="UTC")
DEV_END = pd.Timestamp("2026-09-24", tz="UTC")


def load_main() -> pd.DataFrame:
    d = pd.read_parquet(FILLS)
    d = d[d.sym.isin(MAJORS) & d.x1.isin(R2)].copy()
    d["t_fill"] = pd.to_datetime(d["t_fill"], utc=True)
    d["t_exit"] = pd.to_datetime(d["t_exit"], utc=True)
    d = d[d.t_fill < DEV_END].copy()
    d["T"] = d["t_fill"] - pd.to_timedelta(d["f"], unit="min")
    return d.reset_index(drop=True)


def weights_for_anchor(hist: pd.DataFrame):
    """Return (weights dict, scores dict, fallback bool, per-coin n)."""
    scores, ns = {}, {}
    for c in MAJORS:
        v = hist.loc[hist.sym == c, "y1.0"].to_numpy(dtype=float)
        ns[c] = int(v.size)
        if v.size >= 30:
            mu = float(np.mean(v))
            sd = float(np.std(v, ddof=1))
            if np.isfinite(mu) and np.isfinite(sd) and sd > 0:
                scores[c] = mu / sd
            else:
                scores[c] = float("nan")
        else:
            scores[c] = float("nan")
    finite = {c: s for c, s in scores.items() if np.isfinite(s)}
    if len(finite) < 5 or not np.isfinite(np.mean(list(finite.values()))) \
            or float(np.mean(list(finite.values()))) <= 0:
        return {c: 1.0 for c in MAJORS}, scores, True, ns
    m = float(np.mean([scores[c] for c in MAJORS]))
    raw = {c: (float(np.clip(scores[c] / m, 0.5, 1.5))
               if np.isfinite(scores[c]) else 1.0) for c in MAJORS}
    mean_raw = float(np.mean([raw[c] for c in MAJORS]))
    w = {c: raw[c] / mean_raw for c in MAJORS}
    return w, scores, False, ns


def daily_path(tfills: pd.Series, vals: np.ndarray):
    days = pd.to_datetime(tfills).dt.floor("D")
    s = pd.Series(np.asarray(vals, float)).groupby(days.values).sum().sort_index()
    cum = s.cumsum().to_numpy()
    peak = np.maximum(0.0, np.maximum.accumulate(cum) if len(cum) else 0.0)
    dd = peak - cum
    return s, float(s.min()) if len(s) else 0.0, float(dd.max()) if len(dd) else 0.0


def main() -> dict:
    d = load_main()
    years = []
    for k, a0 in enumerate(ANCHORS):
        hist = d[(d.t_fill > HIST_START) & (d.t_fill < a0 - EMBARGO)]
        w, scores, fallback, ns = weights_for_anchor(hist)
        te = d[(d.t_fill >= a0) & (d.t_fill < a0 + pd.Timedelta(days=365))].copy()
        y = te["y1.0"].to_numpy(dtype=float)
        wv = te["sym"].map(w).to_numpy(dtype=float)
        Su = float(np.sum(y)) if len(y) else 0.0
        Sw = float(np.sum(wv * y)) if len(y) else 0.0
        win = float(np.mean(y > 0)) if len(y) else float("nan")
        _, worst_u, mdd_u = daily_path(te["t_fill"], y)
        _, worst_w, mdd_w = daily_path(te["t_fill"], wv * y)
        coin_n = {c: int((te.sym == c).sum()) for c in MAJORS}
        coin_mean_bps = {c: (round(float(te.loc[te.sym == c, "y1.0"].mean() * 1e4), 2)
                             if coin_n[c] else None) for c in MAJORS}
        years.append({
            "year": str(a0.date()), "n": int(len(te)), "n_per_coin": coin_n,
            "n_hist_per_coin": ns, "fallback": fallback,
            "scores": {c: (round(float(scores[c]), 6) if np.isfinite(scores[c]) else None)
                       for c in MAJORS},
            "weights": {c: round(float(w[c]), 6) for c in MAJORS},
            "S_u": round(Su, 6), "S_w": round(Sw, 6),
            "ratio_Sw_Su": (round(Sw / Su, 6) if Su != 0 else None),
            "pass_sum95": bool(Sw >= 0.95 * Su),
            "win_rate": round(win, 6),
            "worst_day_u": round(float(worst_u), 6),
            "worst_day_w": round(float(worst_w), 6),
            "maxDD_u": round(float(mdd_u), 6), "maxDD_w": round(float(mdd_w), 6),
            "pass_dd": bool(mdd_w <= mdd_u),
            "mean_y_bps_per_coin": coin_mean_bps,
        })
    n_dd = sum(1 for r in years if r["pass_dd"])
    n_sum = sum(1 for r in years if r["pass_sum95"])
    res = {
        "name": "oc_coinwf",
        "anchors": [str(a.date()) for a in ANCHORS],
        "universe": {"majors": MAJORS, "rungs": list(R2), "rows": int(len(d)),
                     "outcome": "y1.0"},
        "years": years,
        "rule": {"pass_dd_years": n_dd, "pass_sum95_years": n_sum,
                 "need": ">=4/5 each",
                 "promising": bool(n_dd >= 4 and n_sum >= 4)},
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))
    return res


if __name__ == "__main__":
    main()
