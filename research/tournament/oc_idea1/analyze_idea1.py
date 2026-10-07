"""oc_idea1: Late-fill fast-TP (TP 0.5 sigma if f >= 209 else 1.0 sigma).

Universe: majors R2 rungs from fills_U_ext joined to oc_b1shape fills_n
(n25, no 1m read). Per PLAN.md: descriptive early/late bucket means of
y0.5/y1.0; rule B (TP 0.5 iff late) vs rule A (always 1.0) at sizes 1/(1+n)
with per-year equal-exposure rescale; D = S_B - S_A per year and
leave-one-year-out means; worst-day gate. Writes results.json.
One process, small frames, RAM < 1 GB.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
OUT = HERE / "results.json"
EXT = Path("research/tournament/ext/fills_U_ext.parquet")
FILLS_N = Path("research/tournament/oc_b1shape/fills_n.parquet")

MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
LATE_MIN = 209  # fixed from oc_filltime: last 30 fillable minutes of 16..238
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in (
    "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
YEAR_D = pd.Timedelta(days=365)


def maxdd(cum: np.ndarray) -> float:
    return float(np.min(cum - np.maximum.accumulate(cum))) if len(cum) else 0.0


def main() -> None:
    fills = pd.read_parquet(EXT)
    fills["Bx"] = fills["t_fill"] - pd.to_timedelta(fills["f"], unit="min")
    fills["k"] = fills["x1"]
    m = fills[fills["sym"].isin(MAJORS) & fills["k"].isin(R2)].copy()
    print(f"majors R2 fills (all dates): {len(m)}", flush=True)

    n = pd.read_parquet(FILLS_N)
    key_l = m[["sym", "Bx", "t_fill", "f", "k", "y0.5", "y1.0", "y1.5"]].copy()
    key_r = n.rename(columns={"Tbar": "Bx"})[["sym", "Bx", "t_fill", "f", "k", "y1.0", "n25"]]
    d = key_l.merge(key_r, on=["sym", "Bx", "t_fill", "f", "k"],
                    suffixes=("", "_n"), how="inner")
    print(f"joined rows: {len(d)} (n rows {len(n)}, majors-R2 rows {len(key_l)})", flush=True)
    assert len(d) > 0
    mismatch = np.abs(d["y1.0"].to_numpy(float) - d["y1.0_n"].to_numpy(float)).max()
    print(f"max |y1.0 - y1.0_n|: {mismatch}", flush=True)
    assert mismatch < 1e-12
    d = d.drop(columns=["y1.0_n"])
    d = d.rename(columns={"n25": "n"})
    assert d["n"].between(0, 4).all()
    assert d["f"].between(16, 238).all()
    d["late"] = (d["f"].to_numpy() >= LATE_MIN)

    d["year"] = -1
    for i, a in enumerate(ANCHORS):
        d.loc[(d["Bx"] >= a) & (d["Bx"] < a + YEAR_D), "year"] = i
    n_outside = int((d["year"] < 0).sum())
    d = d[d["year"] >= 0].reset_index(drop=True)
    print("rows in 5y:", len(d), d["year"].value_counts().sort_index().to_dict(),
          f"dropped outside: {n_outside}", flush=True)

    # 1) descriptive bucket table: early (f<209) vs late (f>=209)
    bucket_table = {}
    for i, a in enumerate(ANCHORS):
        di = d[d["year"] == i]
        row = {}
        for name, mask in (("early", ~di["late"].to_numpy()), ("late", di["late"].to_numpy())):
            db = di[mask]
            diff = (db["y0.5"] - db["y1.0"])
            row[name] = {
                "n": int(len(db)),
                "share": round(float(len(db) / len(di)), 4) if len(di) else None,
                "mean_y05": round(float(db["y0.5"].mean()), 6) if len(db) else None,
                "mean_y10": round(float(db["y1.0"].mean()), 6) if len(db) else None,
                "mean_y15": round(float(db["y1.5"].mean()), 6) if len(db) else None,
                "mean_d05_10": round(float(diff.mean()), 6) if len(db) else None,
                "win_y10": round(float((db["y1.0"] > 0).mean()), 4) if len(db) else None,
            }
        bucket_table[str(a.date())] = row
    overall = {}
    for name, mask in (("early", ~d["late"].to_numpy()), ("late", d["late"].to_numpy())):
        db = d[mask]
        diff = (db["y0.5"] - db["y1.0"])
        overall[name] = {
            "n": int(len(db)),
            "share": round(float(len(db) / len(d)), 4),
            "mean_y05": round(float(db["y0.5"].mean()), 6),
            "mean_y10": round(float(db["y1.0"].mean()), 6),
            "mean_y15": round(float(db["y1.5"].mean()), 6),
            "mean_d05_10": round(float(diff.mean()), 6),
            "win_y10": round(float((db["y1.0"] > 0).mean()), 4),
        }
    bucket_table["overall"] = overall

    # 2) rule test at sizes 1/(1+n), equal exposure per year
    nn = d["n"].to_numpy(float)
    w = 1.0 / (1.0 + nn)
    late = d["late"].to_numpy()
    yA = d["y1.0"].to_numpy(float)
    yB = np.where(late, d["y0.5"].to_numpy(float), yA)
    day = d["Bx"].dt.floor("D")

    rules = {}
    for name, y in (("always1.0", yA), ("tp05_if_late", yB)):
        ys, wd = [], []
        parts = []
        for i in range(5):
            mi = (d["year"] == i).to_numpy()
            wi = w[mi] / w[mi].mean()
            ci = y[mi] * wi
            ys.append(round(float(ci.sum()), 4))
            dd = pd.Series(ci).groupby(day[mi].to_numpy()).sum()
            parts.append(dd)
            wd.append(round(float(dd.min()), 4))
        dall = pd.concat(parts).sort_index()
        cum = dall.cumsum().to_numpy()
        rules[name] = {
            "yearly_S": ys,
            "worst_day_per_year": wd,
            "worst_day_overall": round(float(dall.min()), 4),
            "maxDD_fullpath": round(maxdd(cum), 4),
            "n_fills": int(len(d)),
        }

    D = [round(b - a, 4) for a, b in zip(rules["always1.0"]["yearly_S"], rules["tp05_if_late"]["yearly_S"])]
    n_pos = int(sum(v > 0 for v in D))
    loo = []
    for i in range(5):
        others = [D[j] for j in range(5) if j != i]
        loo.append(round(float(np.mean(others)), 4))
    n_loo_pos = int(sum(v > 0 for v in loo))
    wdA = rules["always1.0"]["worst_day_per_year"]
    wdB = rules["tp05_if_late"]["worst_day_per_year"]
    wd_not_worse = [bool(b >= a) for a, b in zip(wdA, wdB)]
    n_wd = int(sum(wd_not_worse))
    late_share = [round(float(d[d["year"] == i]["late"].mean()), 4) for i in range(5)]
    promising = bool(n_pos >= 4 and n_loo_pos >= 4 and n_wd >= 4)
    verdict = ("PROMISING: conditional TP 0.5 (f>=209) beats always-1.0 "
               f"in {n_pos}/5y with LOO>0 in {n_loo_pos}/5 and worst-day-not-worse in {n_wd}/5."
               if promising else
               "NOT PROMISING: conditional TP 0.5 (f>=209) fails the >=4/5-year "
               f"and LOO>=4/5 and worst-day>=4/5 rule (years>0: {n_pos}/5, LOO>0: {n_loo_pos}/5, worst-day-not-worse: {n_wd}/5).")

    res = {
        "universe": "majors R2 rungs, T in 5 anchor years 2021-09-24..2026-09-23; n=n25 reused from oc_b1shape for weights only; TP rule on f>=209",
        "late_threshold": LATE_MIN,
        "n_fills_5y": int(len(d)),
        "fills_per_year": {str(a.date()): int((d["year"] == i).sum()) for i, a in enumerate(ANCHORS)},
        "late_share_per_year": {str(a.date()): late_share[i] for i, a in enumerate(ANCHORS)},
        "bucket_means": bucket_table,
        "rules": rules,
        "D_tp05_if_late_minus_always10": D,
        "years_positive": n_pos,
        "loo_mean_D": loo,
        "loo_positive": n_loo_pos,
        "worst_day_not_worse_per_year": wd_not_worse,
        "worst_day_not_worse_count": n_wd,
        "promising": promising,
        "verdict": verdict,
        "notes": ("w=1/(1+n) rescaled to mean 1 per year; S=sum(w'*y_rule); "
                  "days by T.floor(D); maxDD on full-path cumsum of daily sums; "
                  "yB=y0.5 if f>=209 else y1.0; n used for weights only."),
    }
    OUT.write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1), flush=True)


if __name__ == "__main__":
    main()
