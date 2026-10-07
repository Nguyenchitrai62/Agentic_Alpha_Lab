"""oc_phasedisp: single-clock dispersion of deployment config R2B1D17BFG2.

Each phase (clock shift 0..3h) is scored alone as if a user ran that single
clock, using the reset metric from research/diagnostics/r2_decompose5/reset_metric.py
restricted to one phase: per anchor year the phase equity is rebased to 1.0 at the
anchor (value at/below anchor), R = 100*(end**(1/12)-1), DD = peak-to-marked-trough
inside that year segment. The 4-phase mix (each sub-account reset to 1/4 of the
capital at each anchor) is shown next to the single phases. Full-path DD follows
v421 (no per-year reset, from 2021-09-24, max of marked series vs running peak).

Reads: research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl
Writes: results.json (this folder)
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RUNS_PKL = ROOT / "research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl"
STRAT = "R2B1D17BFG2"
ANCH = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
G0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
G1 = Y1 + pd.Timedelta(hours=12)


def hourly(run, g0=G0, g1=G1):
    # identical to v388_bot_stop_distance.hourly
    t = pd.to_datetime(run["t"], utc=True)
    grid = pd.date_range(g0, g1, freq="1h")
    e = pd.Series(run["eq"], index=t).reindex(grid, method="ffill").fillna(1.0)
    lo = pd.Series(run["eq_min"], index=t - pd.Timedelta(hours=4)).reindex(grid, method="ffill").fillna(1.0)
    return e, np.minimum(lo, e)


def year_reset_single(run, y):
    # reset_metric.year_reset logic restricted to one phase
    e1, m1 = hourly(run, G0, G1)
    a0 = pd.Timestamp(ANCH[y], tz="UTC")
    b = float(e1[e1.index <= a0].iloc[-1]) if (e1.index <= a0).any() else 1.0
    seg = (e1.index > a0) & (e1.index <= a0 + pd.Timedelta(days=365))
    es, ms = e1[seg] / b, m1[seg] / b
    pk = np.maximum.accumulate(es.to_numpy())
    return dict(R=round(100 * float(es.iloc[-1] ** (1 / 12) - 1), 3),
                DD=round(100 * float(np.max(1 - ms.to_numpy() / pk)), 2))


def year_reset_mix(runs, strat, y):
    # identical to reset_metric.year_reset (4 sub-accounts reset to 1/4 each anchor)
    E, MN = [], []
    for s in range(4):
        e1, m1 = hourly(runs[s][strat], G0, G1)
        a0 = pd.Timestamp(ANCH[y], tz="UTC")
        b = float(e1[e1.index <= a0].iloc[-1]) if (e1.index <= a0).any() else 1.0
        seg = (e1.index > a0) & (e1.index <= a0 + pd.Timedelta(days=365))
        E.append(e1[seg] / b)
        MN.append(m1[seg] / b)
    es, ms = sum(E) / 4, sum(MN) / 4
    pk = np.maximum.accumulate(es.to_numpy())
    return dict(R=round(100 * float(es.iloc[-1] ** (1 / 12) - 1), 3),
                DD=round(100 * float(np.max(1 - ms.to_numpy() / pk)), 2))


def summarize(year_dicts):
    rs = [d["R"] for d in year_dicts]
    geo = 100 * (np.prod([1 + r / 100 for r in rs]) ** (1 / len(rs)) - 1)
    return dict(mean_5y=round(float(geo), 3), worst=min(rs),
                max_yearly_dd=max(d["DD"] for d in year_dicts),
                losing=sum(r < 0 for r in rs))


def full_path_dd_single(run):
    e, mn = hourly(run, G0, G1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    return round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)


def full_path_dd_mix(runs, strat):
    hs = [hourly(runs[s][strat], G0, G1) for s in range(4)]
    e = sum(h[0] for h in hs) / 4
    mn = sum(h[1] for h in hs) / 4
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    return round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)


def main():
    runs = pickle.loads(RUNS_PKL.read_bytes())
    out = {"strat": STRAT, "anchors": list(ANCH), "metric": "reset per anchor to 1.0 (mix: 4x1/4 reset), R=monthly %/month, DD=year-segment marked DD; full_path_dd from 2021-09-24 no reset",
           "phases": {}, "mix": {}}
    for s in range(4):
        yrs = [year_reset_single(runs[s][STRAT], y) for y in range(5)]
        sm = summarize(yrs)
        sm["full_path_dd"] = full_path_dd_single(runs[s][STRAT])
        sm["years"] = yrs
        out["phases"][str(s)] = sm
    myrs = [year_reset_mix(runs, STRAT, y) for y in range(5)]
    mm = summarize(myrs)
    mm["full_path_dd"] = full_path_dd_mix(runs, STRAT)
    mm["years"] = myrs
    out["mix"] = mm
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    for s in range(4):
        p = out["phases"][str(s)]
        print(f"phase{s}", [(d["R"], d["DD"]) for d in p["years"]], "mean", p["mean_5y"], "worst", p["worst"], "maxDD", p["max_yearly_dd"], "full", p["full_path_dd"])
    print("mix", [(d["R"], d["DD"]) for d in mm["years"]], "mean", mm["mean_5y"], "worst", mm["worst"], "maxDD", mm["max_yearly_dd"], "full", mm["full_path_dd"])


if __name__ == "__main__":
    main()
