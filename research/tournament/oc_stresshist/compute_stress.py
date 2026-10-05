"""oc_stresshist: stress-window table for R2B1D17BFG2 (v421) vs R2B1D17BF (v411).

REPORTING only. Light: one process, two small runs pkls, no 1m data.
Method exactly as PLAN.md (reset-at-anchor yearly paths, v388.hourly grid).

  python research/tournament/oc_stresshist/compute_stress.py
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_for_stresshist", RD / "v388" / "v388_bot_stop_distance.py")
ANCH = v388.ANCH
G1 = v388.Y1 + pd.Timedelta(hours=12)

CFG = {
    "G2": (RD / "v421" / "v421_runs.pkl", "R2B1D17BFG2"),
    "D17BF": (RD / "v411" / "v411_runs.pkl", "R2B1D17BF"),
}

NAMED = [
    ("2021-12-04", "2021-12-04", "2021-12-11"),
    ("LUNA 2022-05-09..05-15", "2022-05-09", "2022-05-16"),
    ("3AC 2022-06-13..06-19", "2022-06-13", "2022-06-20"),
    ("FTX 2022-11-07..11-14", "2022-11-07", "2022-11-15"),
    ("2023-08-17", "2023-08-17", "2023-08-24"),
    ("2024-01-03", "2024-01-03", "2024-01-10"),
    ("2024-03-05", "2024-03-05", "2024-03-12"),
    ("2024-08-04..08-07", "2024-08-04", "2024-08-08"),
    ("2025-10-10..10-11", "2025-10-10", "2025-10-12"),
]


def yearly_paths(pkl_path, strat):
    """Return {y: (es, ms)} reset-at-anchor yearly hourly Series (mean of 4 phases)."""
    import pickle

    runs = pickle.loads(Path(pkl_path).read_bytes())
    g0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
    out = {}
    for y in range(5):
        a0 = pd.Timestamp(ANCH[y], tz="UTC")
        E, MN = [], []
        for s in range(4):
            e1, m1 = v388.hourly(runs[s][strat], g0, G1)
            b = float(e1[e1.index <= a0].iloc[-1]) if (e1.index <= a0).any() else 1.0
            seg = (e1.index > a0) & (e1.index <= a0 + pd.Timedelta(days=365))
            E.append(e1[seg] / b)
            MN.append(m1[seg] / b)
        out[y] = (sum(E) / 4, sum(MN) / 4)
    return out


def year_of(ts):
    ts = pd.Timestamp(ts, tz="UTC")
    for y in range(5):
        a0 = pd.Timestamp(ANCH[y], tz="UTC")
        if a0 < ts <= a0 + pd.Timedelta(days=365):
            return y
    raise ValueError(f"timestamp outside 5 anchor years: {ts}")


def _ts(x):
    t = pd.Timestamp(x)
    return t if t.tzinfo is not None else t.tz_localize("UTC")


def score_window(es, ms, anchor, w0, w1):
    """Metrics of window [w0, w1) on a reset-year path. Pure function (tested)."""
    w0, w1 = _ts(w0), _ts(w1)
    seg = es[(es.index >= w0) & (es.index < w1)]
    start = float(es[es.index <= w0].iloc[-1])
    trough = float(seg.min())
    t_trough = seg.idxmin()
    peak = float(es[(es.index >= anchor) & (es.index <= t_trough)].max())
    dd = 100 * (1 - trough / peak)
    after = es[(es.index >= t_trough) & (es.index <= anchor + pd.Timedelta(days=365))]
    hit = after[after >= peak]
    rec = None if len(hit) == 0 else round((hit.index[0] - t_trough).total_seconds() / 86400, 2)
    week_ret = 100 * (float(seg.iloc[-1]) / start - 1)
    return dict(
        start=round(start, 4),
        trough=round(trough, 4),
        t_trough=str(t_trough),
        peak=round(peak, 4),
        dd=round(dd, 2),
        rec_days=rec,
        week_ret=round(week_ret, 2),
    )


def worst_weeks(by_year, n=5, sep_days=7):
    """Greedy worst non-overlapping 7-day windows. Pure (tested).

    by_year: {y: es} reset-year paths. Lookbacks never cross an anchor
    (first 7 d of each year are ineligible as window ends).
    """
    cands = []  # (ret, t)
    for y, es in by_year.items():
        a0 = pd.Timestamp(ANCH[y], tz="UTC")
        lah = es / es.shift(24 * 7) - 1  # hourly grid -> 7d
        lah = lah[lah.index >= a0 + pd.Timedelta(days=7)].dropna()
        for t, v in lah.items():
            cands.append((float(v), t))
    cands.sort(key=lambda x: x[0])
    picked = []
    for r, t in cands:
        if all(abs((t - p).total_seconds()) >= sep_days * 86400 for _, p in picked):
            picked.append((r, t))
        if len(picked) == n:
            break
    return [dict(w0=str(t - pd.Timedelta(days=7)), w1=str(t),
                 ret7=round(100 * r, 2)) for r, t in picked]


def main():
    paths = {k: yearly_paths(p, s) for k, (p, s) in CFG.items()}
    res = {"configs": {k: {"pkl": str(v[0].relative_to(ROOT)), "strat": v[1]}
                       for k, v in CFG.items()},
           "method": ("4-phase mean of v388.hourly paths, each phase /value@anchor, "
                      "yearly reset to 1.0; dd from pre-trough peak of same year; "
                      "recovery searched to year end"),
           "named": [], "worst_weeks": []}
    for name, d0, d1 in NAMED:
        y = year_of(d0)
        a0 = pd.Timestamp(ANCH[y], tz="UTC")
        row = dict(window=name, w0=d0, w1=d1, anchor_year=y)
        for k in ("G2", "D17BF"):
            es, ms = paths[k][y]
            row[k] = score_window(es, ms, a0, d0, d1)
        row["diff"] = dict(
            trough_G2_minus_BF=round(row["G2"]["trough"] - row["D17BF"]["trough"], 4),
            dd_G2_minus_BF_pp=round(row["G2"]["dd"] - row["D17BF"]["dd"], 2),
            rec_G2_minus_BF_days=(None if row["G2"]["rec_days"] is None
                                  or row["D17BF"]["rec_days"] is None
                                  else round(row["G2"]["rec_days"] - row["D17BF"]["rec_days"], 2)),
        )
        res["named"].append(row)

    ww = {k: worst_weeks({y: paths[k][y][0] for y in range(5)})
          for k in ("G2", "D17BF")}
    res["worst_weeks"] = {}
    for k in ("G2", "D17BF"):
        rows = []
        for w in ww[k]:
            y = year_of(w["w0"])
            a0 = pd.Timestamp(ANCH[y], tz="UTC")
            row = dict(w0=w["w0"], w1=w["w1"], anchor_year=y, ret7=w["ret7"])
            for c in ("G2", "D17BF"):
                es, ms = paths[c][y]
                row[c] = score_window(es, ms, a0, w["w0"], w["w1"])
            row["diff"] = dict(
                trough_G2_minus_BF=round(row["G2"]["trough"] - row["D17BF"]["trough"], 4),
                dd_G2_minus_BF_pp=round(row["G2"]["dd"] - row["D17BF"]["dd"], 2),
                rec_G2_minus_BF_days=(None if row["G2"]["rec_days"] is None
                                      or row["D17BF"]["rec_days"] is None
                                      else round(row["G2"]["rec_days"] - row["D17BF"]["rec_days"], 2)),
            )
            rows.append(row)
        res["worst_weeks"][f"worst5_of_{k}"] = rows
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(f"named={len(res['named'])}")
    for r in res["named"]:
        print(r["window"], "G2 dd", r["G2"]["dd"], "BF dd", r["D17BF"]["dd"],
              "dDiff", r["diff"]["dd_G2_minus_BF_pp"])
    for k, rows in res["worst_weeks"].items():
        for w in rows:
            print(k, w["w0"], "->", w["w1"], "ret7", w["ret7"],
                  "G2 dd", w["G2"]["dd"], "BF dd", w["D17BF"]["dd"])


if __name__ == "__main__":
    main()
