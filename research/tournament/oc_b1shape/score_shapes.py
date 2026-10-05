"""oc_b1shape: score S0/S1 + 3 pre-registered shapes (harness5-style, equal exposure).

Per year (anchors 2021-09-24..2025-09-24, [a, a+365d) keyed by T): rescale raw
weights to mean 1, S = sum(w' * y1.0); worst-day from T.floor('D') groups;
full-path maxDD of cumsum of daily sums. Writes results.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
IN = HERE / "fills_n.parquet"
OUT = HERE / "results.json"
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in (
    "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
YEAR_D = pd.Timedelta(days=365)


def shapes(d: pd.DataFrame) -> dict:
    n = d.n25.to_numpy(float)
    n2 = d.n20.to_numpy(float)
    nw = n + np.where(d.sym.to_numpy() != "BTCUSDT", d.btc_det.to_numpy(float), 0.0)
    return {
        "S0_flat": np.ones(len(d)),
        "S1_inv1pn": 1.0 / (1.0 + n),
        "S2_inv1pn2": 1.0 / (1.0 + n) ** 2,
        "S3_btc2x": 1.0 / (1.0 + nw),
        "S4_thresh20": 1.0 / (1.0 + n2),
    }


def maxdd(cum: np.ndarray) -> float:
    return float(np.min(cum - np.maximum.accumulate(cum))) if len(cum) else 0.0


def main():
    d = pd.read_parquet(IN)
    d["year"] = -1
    for i, a in enumerate(ANCHORS):
        d.loc[(d["Tbar"] >= a) & (d["Tbar"] < a + YEAR_D), "year"] = i
    d = d[d.year >= 0].reset_index(drop=True)
    print("rows in 5y:", len(d), d.year.value_counts().sort_index().to_dict(), flush=True)

    hist = {}
    for i, a in enumerate(ANCHORS):
        v = d[d.year == i].n25.value_counts(normalize=True).sort_index()
        hist[str(a.date())] = {str(k): round(float(v.get(k, 0.0)), 4) for k in range(5)}
    vall = d.n25.value_counts(normalize=True).sort_index()
    hist["overall"] = {str(k): round(float(vall.get(k, 0.0)), 4) for k in range(5)}
    hist["counts_per_year"] = {str(a.date()): {str(k): int((d[d.year == i].n25 == k).sum()) for k in range(5)}
                               for i, a in enumerate(ANCHORS)}

    W = shapes(d)
    y = d["y1.0"].to_numpy(float)
    day = d["Tbar"].dt.floor("D")
    per_shape, daily_all = {}, {}
    for name, w in W.items():
        w = np.asarray(w, float)
        ys, wd = [], []
        dall = []
        for i, a in enumerate(ANCHORS):
            m = (d.year == i).to_numpy()
            wi = w[m] / w[m].mean()
            ci = y[m] * wi
            S = float(ci.sum())
            dd = pd.Series(ci).groupby(day[m].to_numpy()).sum()
            dall.append(dd)
            ys.append(round(S, 4))
            wd.append(round(float(dd.min()), 4))
        dall = pd.concat(dall).sort_index()
        cum = dall.cumsum().to_numpy()
        row = {"yearly_S": ys, "worst_day_per_year": wd,
               "worst_day_overall": round(float(dall.min()), 4),
               "maxDD_fullpath": round(maxdd(cum), 4),
               "n_fills": int(len(d))}
        per_shape[name] = row
        daily_all[name] = dall

    s1 = per_shape["S1_inv1pn"]["yearly_S"]
    qual = {}
    for name, row in per_shape.items():
        if name == "S1_inv1pn":
            qual[name] = True
        else:
            qual[name] = bool(sum(a >= b for a, b in zip(row["yearly_S"], s1)) >= 4)
    cands = {k: v for k, v in per_shape.items() if qual[k]}
    best_wd = max(cands, key=lambda k: cands[k]["worst_day_overall"])
    best_dd = max(cands, key=lambda k: cands[k]["maxDD_fullpath"])
    verdict = (f"keep S1 ({best_wd}/{best_dd} only win if strictly better tails)"
               if best_wd == "S1_inv1pn" and best_dd == "S1_inv1pn"
               else f"winner by tails under S>=S1-in->=4y: worst-day {best_wd}, maxDD {best_dd}")
    # strict: a challenger must beat S1 tails outright to displace it
    if best_wd != "S1_inv1pn" and not (per_shape[best_wd]["worst_day_overall"] > per_shape["S1_inv1pn"]["worst_day_overall"]):
        best_wd = "S1_inv1pn"
    if best_dd != "S1_inv1pn" and not (per_shape[best_dd]["maxDD_fullpath"] > per_shape["S1_inv1pn"]["maxDD_fullpath"]):
        best_dd = "S1_inv1pn"
    winner = best_wd if best_wd == best_dd else f"{best_wd} (worst-day) / {best_dd} (maxDD)"
    if winner.startswith("S1_inv1pn"):
        verdict = "keep S1: no pre-registered shape beats its tails under yearly-S>=S1 in >=4/5y."
    else:
        verdict = f"adopt {winner}: beats S1 tails with yearly-S>=S1 in >=4/5y."

    res = {"n_hist_share": hist, "shapes": per_shape,
           "qualifies_S_ge_S1_in_ge4y": qual,
           "best_worst_day": best_wd, "best_maxDD": best_dd,
           "verdict": verdict,
           "notes": "equal-exposure per year (mean w'=1); S=sum(w'*y1.0); days by T.floor(D); maxDD on full-path cumsum of daily sums."}
    OUT.write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1), flush=True)


if __name__ == "__main__":
    main()
