"""Diagnostic (first four walk-forward years only, not registered): do dip-rung outcomes of v269 M1 depend on the funding / premium state
at the decision? Buckets (quintiles computed within each dev year, so no level drift) of the predicted funding pf_pred and the premium
z-score pf_prem_z (v231/premium_features.py, known at the decision-bar close) -> mean net return per filled rung, stop share, n.
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
pfm = _load("pfm", RD / "v231/premium_features.py")
eu, v216 = v221.eu, v221.v216
books154, opens = eu.er.v154_books()
cols, idx = list(books154.columns), books154.index
Cc = eu.er.CACHE
m = {k: pd.read_parquet(Cc / f).reindex(idx).fillna(0.0)[cols] for k, f in (
    ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
books = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
prep = eu.prepare(books154, opens)
ev = []
eu.simulate(books, opens, prep, trade=dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL)), win_start=5, events=ev,
            **dict(v221.KW, sleeve_risk_budget=0.18, sleeve_stop_mode="close5", sleeve_backstop=8.0, m_sleeve_sl=4.0))
t_hold = idx + pd.Timedelta(hours=4)
anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
pf = {s: pfm.premium_features(s, idx) for s in cols}
rows, last = [], None
for e in ev:
    if e["kind"] == "rung_fill":
        last = e
    elif e["kind"] in ("rung_tp", "rung_sl", "rung_timeout") and last is not None:
        t0 = last["t"].floor("4h")
        i = int(np.searchsorted(t_hold, t0))
        if anchors[0] <= t_hold[i] < anchors[4]:
            s = last["symbol"]
            rows.append(dict(year=max(j for j, a0 in enumerate(anchors) if t_hold[i] >= a0), ret=float(e["ret"]), sl=e["kind"] == "rung_sl",
                             pred=float(pf[s]["pf_pred"].iloc[i]), prem_z=float(pf[s]["pf_prem_z"].iloc[i])))
        last = None
d = pd.DataFrame(rows).dropna()
out = {}
for col in ("pred", "prem_z"):
    d["q"] = d.groupby("year")[col].transform(lambda x: pd.qcut(x.rank(method="first"), 5, labels=False))
    res = {}
    for y in range(4):
        g = d[d.year == y]
        res[str(anchors[y].year)] = [round(100 * float(g[g.q == q].ret.mean()), 3) for q in range(5)]
    res["all_n"] = [int((d.q == q).sum()) for q in range(5)]
    res["all_stop_share"] = [round(float(d[d.q == q].sl.mean()), 3) for q in range(5)]
    out[col] = res
    print(col, "mean net % by quintile (low -> high) per dev year", json.dumps(res))
Path("research/diagnostics/dip_funding/dip_funding_dev.json").write_text(json.dumps(out, indent=1))
