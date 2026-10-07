"""oc_beartp: bear-regime faster dip take-profit (idea #14).

Frozen PLAN.md definitions. LIGHT: hourly data only, one process, < 1 GB.
Regime = v410 bear flag (BTC 4h open < mean of last 1200 4h opens incl. T,
min 600; strict; NaN-MA -> non-bear), causal at the bar open.
Rule: bear bars -> TP 0.5 sigma; non-bear -> deployed tp_dep.
Sizes fixed at size_dep; outcomes y0.5 vs y_dep from harness5.load.
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

OUT = ROOT / "research" / "tournament" / "oc_beartp"
HOURLY = H5.HOURLY
MAJORS = H5.MAJORS
R2 = H5.R2
ANCHORS = H5.ANCHORS
DEV_END = H5.DEV_END
GRID_HOURS = (0, 4, 8, 12, 16, 20)
WIN, MINP = 1200, 600
EPS = 1e-9


def load_btc_4h_opens() -> pd.Series:
    """BTC 4h opens from hourly_ext (t = bar START), t < DEV_END, 4h grid."""
    h = pd.read_parquet(HOURLY, columns=["t", "open", "sym"])
    h = h[(h["sym"] == "BTCUSDT") & (h["t"] < DEV_END)].copy()
    h["t"] = pd.to_datetime(h["t"], utc=True)
    h = h[(h["t"].dt.hour.isin(GRID_HOURS)) & (h["t"].dt.minute == 0)]
    h = h.sort_values("t").drop_duplicates("t").reset_index(drop=True)
    return pd.Series(h["open"].to_numpy(float), index=pd.DatetimeIndex(h["t"]))


def bear_from_opens(opens: pd.Series) -> pd.Series:
    """v410 bear flag: open[T] < rolling-1200 mean incl. T (min 600)."""
    ma = opens.rolling(WIN, min_periods=MINP).mean()
    return ((opens < ma) & ma.notna() & opens.notna()).fillna(False)


def maxdd_of_daily_sums(days: np.ndarray, vals: np.ndarray) -> float:
    """Absolute max drawdown of the cumulative daily-sum path from 0."""
    s = pd.Series(np.asarray(vals, float)).groupby(np.asarray(days)).sum()
    s = s.sort_index()
    c = np.concatenate([[0.0], np.cumsum(s.to_numpy(float))])
    peak = np.maximum.accumulate(c)
    return float(np.max(peak - c))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    d = H5.load()
    d["T"] = pd.to_datetime(d["T"], utc=True)

    opens = load_btc_4h_opens()
    bear_s = bear_from_opens(opens)
    bear_map = dict(zip(opens.index, bear_s.to_numpy(bool)))
    ma_map = dict(zip(opens.index, opens.rolling(WIN, min_periods=MINP).mean().to_numpy(float)))

    is_r2 = (d["sym"].isin(MAJORS) & d["k"].isin(R2) & d["size_dep"].notna()).to_numpy()
    T = d["T"]
    bear_arr = T.map(bear_map).fillna(False).to_numpy(dtype=bool)

    d["bear"] = bear_arr
    d["open4"] = T.map(dict(zip(opens.index, opens.to_numpy(float)))).astype(float)
    d["ma1200"] = T.map(ma_map).astype(float)
    tp_dep = d["tp_dep"].to_numpy(float)
    tp_new = np.where(bear_arr, 0.5, tp_dep)
    d["tp_new"] = tp_new
    y_dep = d["y_dep"].to_numpy(float)
    y05 = d["y0.5"].to_numpy(float)
    y_new = np.where(bear_arr, y05, y_dep)
    d["y_new"] = y_new

    d[["T", "sym", "x1", "k", "size_dep", "tp_dep", "tp_new",
       "y_dep", "y0.5", "y_new", "bear", "open4", "ma1200"]].to_parquet(
        OUT / "features_beartp.parquet")

    # Independent harness5.score_tp cross-check (sizes fixed at size_dep).
    tp_col = np.full(len(d), np.nan)
    tp_col[is_r2] = tp_new[is_r2]
    ref = H5.score_tp(d, tp_col, name="bear_tp05")

    years_out = []
    for k, a0 in enumerate(ANCHORS):
        te = ((d["T"] >= a0) & (d["T"] < a0 + pd.Timedelta(days=365))).to_numpy() & is_r2
        sd = d["size_dep"].to_numpy(float)[te]
        yd = y_dep[te]
        yn = y_new[te]
        bear_te = bear_arr[te]
        n = int(te.sum())
        n_bear = int(bear_te.sum())
        S_dep = float((sd * yd).sum()) if n else float("nan")
        S_new = float((sd * yn).sum()) if n else float("nan")
        gain = S_new - S_dep if n else float("nan")
        win_dep = float((yd > 0).mean()) if n else float("nan")
        win_new = float((yn > 0).mean()) if n else float("nan")
        win_dep_b = float((yd[bear_te] > 0).mean()) if n_bear else None
        win_new_b = float((yn[bear_te] > 0).mean()) if n_bear else None
        day = d["T"][te].dt.floor("D").to_numpy()
        dd = pd.Series(sd * yd).groupby(day).sum().sort_index()
        dn = pd.Series(sd * yn).groupby(day).sum().sort_index()
        W_dep = float(dd.min()) if n else float("nan")
        W_new = float(dn.min()) if n else float("nan")
        DD_dep = maxdd_of_daily_sums(day, sd * yd) if n else float("nan")
        DD_new = maxdd_of_daily_sums(day, sd * yn) if n else float("nan")
        changed = float((tp_new[te] != tp_dep[te]).mean()) if n else float("nan")
        mean_diff_bear = float((y05[te][bear_te] - yd[bear_te]).mean()) if n_bear else None
        pass_sum = bool(np.isfinite(S_new) and np.isfinite(S_dep) and S_new >= S_dep - EPS)
        pass_dd = bool(np.isfinite(DD_new) and np.isfinite(DD_dep) and DD_new <= DD_dep + EPS)
        ry = ref["years"][k]
        years_out.append({
            "anchor": str(a0.date()), "n": n, "n_bear": n_bear,
            "bear_share": round(n_bear / n, 4) if n else None,
            "changed": round(changed, 4) if np.isfinite(changed) else None,
            "S_dep": round(S_dep, 4), "S_new": round(S_new, 4),
            "gain": round(gain, 4),
            "gain_bps": round(gain * 1e4, 2),
            "sum_not_lower": pass_sum,
            "win_dep": round(win_dep, 4), "win_new": round(win_new, 4),
            "win_dep_bear": round(win_dep_b, 4) if win_dep_b is not None else None,
            "win_new_bear": round(win_new_b, 4) if win_new_b is not None else None,
            "worst_day_dep": round(W_dep, 4), "worst_day_new": round(W_new, 4),
            "DD_dep": round(DD_dep, 4), "DD_new": round(DD_new, 4),
            "dd_not_worse": pass_dd,
            "mean_y05_minus_ydep_bear": round(mean_diff_bear, 6) if mean_diff_bear is not None else None,
            "harness_S_dep": ry["S_dep"], "harness_S_new": ry["S_new"],
            "harness_gain": ry["gain"],
        })

    n_sum = sum(1 for y in years_out if y["sum_not_lower"])
    n_dd = sum(1 for y in years_out if y["dd_not_worse"])
    promising = bool(n_dd >= 4 and n_sum >= 3)
    res = {
        "meta": {
            "fills": str(H5.FILLS), "hourly": str(H5.HOURLY),
            "table": str(H5.TABLE),
            "universe": "majors x R2(2.5,3,3.5,4,5), harness5 test rows",
            "regime": "v410 bear flag: BTC 4h open[T] < mean(open4[T-1199..T]) incl T, min 600; NaN-MA -> non-bear",
            "rule": "bear bars -> TP 0.5 sigma (y0.5); non-bear -> tp_dep/y_dep; sizes fixed at size_dep",
            "outcomes": "y0.5 vs y_dep exact net (fees + adverse funding inside)",
            "dd_def": "max(peak-cum) of cumulative daily-sum path from 0, days by floor(T) UTC",
            "win_def": "unweighted mean(y>0) over test rungs",
            "variant": "single fixed variant, zero fitted parameters",
            "T_min": str(pd.to_datetime(d.loc[is_r2, 'T']).min()),
            "T_max": str(pd.to_datetime(d.loc[is_r2, 'T']).max()),
            "n_4h_opens": int(len(opens)),
            "opens_start": str(opens.index.min()), "opens_end": str(opens.index.max()),
            "unit": "native size*y units; bps x1e4 for gain scale",
        },
        "years": years_out,
        "decision": {
            "dd_not_worse": f"{n_dd}/5",
            "sum_not_lower": f"{n_sum}/5",
            "promising": promising,
        },
    }
    (OUT / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["decision"], indent=1))
    for y in years_out:
        print(y["anchor"], "n", y["n"], "bear", y["n_bear"],
              "S", y["S_dep"], "->", y["S_new"], "sum_ok", y["sum_not_lower"],
              "DD", y["DD_dep"], "->", y["DD_new"], "dd_ok", y["dd_not_worse"],
              "win", y["win_dep"], "->", y["win_new"])


if __name__ == "__main__":
    main()
