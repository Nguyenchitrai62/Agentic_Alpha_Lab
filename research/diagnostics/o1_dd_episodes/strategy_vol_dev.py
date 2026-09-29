"""Diagnostic (first four walk-forward years only, not registered): does the O1 + budget 0.18 strategy's trailing realized volatility
predict its next-30-day return, volatility and drawdown? (Would strategy-level vol targeting improve the return / DD ratio?)"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

RD = Path("research/parallel/rounds/parallel-20260906-r2")
spec = importlib.util.spec_from_file_location("v221", RD / "v221/v221_grid_hysteresis.py")
v221 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v221)
eu, v216 = v221.eu, v221.v216
books154, opens = eu.er.v154_books()
cols, idx = list(books154.columns), books154.index
C = eu.er.CACHE
m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
    ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
books = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
prep = eu.prepare(books154, opens)
trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
cap = {}
orig = eu.summarize
eu.summarize = lambda idx_, net, eq, eq_min, g, stats, eq_max=None: (cap.update(eq=eq.copy(), g=g.copy()), orig(idx_, net, eq, eq_min, g, stats, eq_max))[1]
eu.simulate(books, opens, prep, trade=trade, win_start=5, **dict(v221.KW, sleeve_risk_budget=0.18))
anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
eq = pd.Series(cap["eq"], index=idx + pd.Timedelta(hours=4))
eq = eq[(eq.index >= anchors[0]) & (eq.index < anchors[4])]
d = eq.resample("1D").last().dropna()
r = np.log(d).diff()
rows = []
for k in range(30, len(d) - 30, 7):
    past = r.iloc[k - 29:k + 1]
    fut = d.iloc[k:k + 31]
    rows.append(dict(t=d.index[k], vol=past.std() * np.sqrt(365), g=float(pd.Series(cap["g"], index=idx + pd.Timedelta(hours=4)).asof(d.index[k])),
                     past_ret=float(past.sum()), fut_ret=float(np.log(fut.iloc[-1] / fut.iloc[0])),
                     fut_vol=float(np.log(fut).diff().std() * np.sqrt(365)), fut_dd=float((1 - fut / fut.cummax()).max())))
x = pd.DataFrame(rows)
x["q"] = pd.qcut(x.vol, 5, labels=False)
res = x.groupby("q").agg(n=("vol", "size"), trail_vol=("vol", "mean"), fut_ret_pct=("fut_ret", lambda s: 100 * s.mean()),
                         fut_vol=("fut_vol", "mean"), fut_dd_pct=("fut_dd", lambda s: 100 * s.mean()),
                         fut_dd_max_pct=("fut_dd", lambda s: 100 * s.max())).round(3)
res["ret_per_vol"] = (res.fut_ret_pct / 100 / res.fut_vol).round(3)
print(res.to_string())
print("spearman trail vol vs fut vol", round(x.vol.corr(x.fut_vol, method="spearman"), 3), "vs fut ret", round(x.vol.corr(x.fut_ret, method="spearman"), 3),
      "past ret vs fut ret", round(x.past_ret.corr(x.fut_ret, method="spearman"), 3))
Path("research/diagnostics/o1_dd_episodes/strategy_vol_dev.json").write_text(res.to_json())
yr = x.t.apply(lambda t: max(j for j, a0 in enumerate(anchors) if t >= a0))
for y in range(4):
    s = x[yr == y]
    lo, hi = s.vol <= s.vol.median(), s.vol > s.vol.median()
    print(anchors[y].year, "spearman vol->fut ret", round(s.vol.corr(s.fut_ret, method="spearman"), 3),
          "fut ret calm/volatile %", round(100 * s.fut_ret[lo].mean(), 2), round(100 * s.fut_ret[hi].mean(), 2),
          "fut dd calm/volatile %", round(100 * s.fut_dd[lo].mean(), 2), round(100 * s.fut_dd[hi].mean(), 2))
