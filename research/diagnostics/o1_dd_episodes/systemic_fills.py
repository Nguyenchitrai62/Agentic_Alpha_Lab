"""Diagnostic (first four walk-forward years only): dip-sleeve fills grouped by how SYSTEMIC the dip is at the fill minute.

systemic count = number of distinct coins (including this one) whose ladder already had a fill in the same holding bar at or before this
fill minute (causal: known at the fill). Reports n, mean net return, weighted contribution, stop share and the worst 1% per group.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

RD = Path("research/parallel/rounds/parallel-20260906-r2")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
eu, v216 = v221.eu, v221.v216
books154, opens = eu.er.v154_books()
cols, idx = list(books154.columns), books154.index
C = eu.er.CACHE
m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
    ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
books = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
prep = eu.prepare(books154, opens)
trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
out = {}
for budget in (0.18, 10.0):
    ev = []
    eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev, **dict(v221.KW, sleeve_risk_budget=budget))
    rows, last = [], None
    for e in ev:
        if e["kind"] == "rung_fill":
            last = e
        elif e["kind"] in ("rung_tp", "rung_sl", "rung_timeout") and last is not None:
            rows.append(dict(t=last["t"], sym=last["symbol"], rung=last["rung"], w=last["weight"], ret=e["ret"], kind=e["kind"]))
            last = None
    d = pd.DataFrame(rows)
    d = d[(d.t >= anchors[0]) & (d.t < anchors[4])].copy()
    d["bar"] = d.t.dt.floor("4h")
    d = d.sort_values("t")
    cnt = []
    for _, g in d.groupby("bar"):
        seen = {}
        for t, s in zip(g.t, g.sym):
            seen.setdefault(s, t)
            cnt.append(sum(1 for v in seen.values() if v <= t))
    d["sys"] = np.concatenate([np.array(c) for c in [cnt]])
    res = {}
    for k, g in d.groupby("sys"):
        res[int(k)] = dict(n=len(g), mean_pct=round(100 * g.ret.mean(), 3), contrib_pct=round(100 * (g.w * g.ret).sum(), 2),
                           stop_share=round(float((g.kind == "rung_sl").mean()), 3), q01_pct=round(100 * g.ret.quantile(0.01), 2),
                           worst_bar_contrib_pct=round(100 * float((g.w * g.ret).groupby(g.bar).sum().min()), 2))
    out[str(budget)] = res
    print("budget", budget, json.dumps(res))
Path("research/diagnostics/o1_dd_episodes/systemic_fills.json").write_text(json.dumps(out, indent=1))
