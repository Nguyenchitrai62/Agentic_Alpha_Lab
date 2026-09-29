"""Diagnostic (first four walk-forward years only): where do the O1 + budget 0.18 drawdowns come from - book vs dip sleeve, per coin.

For every year 2021-2024 the deepest 4h-close drawdown episode (peak -> trough) is split into book PnL per coin and sleeve PnL, and the
1m-marked worst bars are listed. The most recent year is not read.
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
att, bars = [], []
cap = {}
orig = eu.summarize


def grab(idx_, net, eq, eq_min, g, stats, eq_max=None):
    cap.update(eq=eq.copy(), eq_min=eq_min.copy(), g=g.copy())
    return orig(idx_, net, eq, eq_min, g, stats, eq_max)


eu.summarize = grab
r = eu.simulate(books, opens, prep, trade=trade, win_start=5, attrib=att, **dict(v221.KW, sleeve_risk_budget=0.18))
print("dev4", r["monthly_dev4"])
t = pd.DatetimeIndex([a[0] for a in att])
book = pd.DataFrame([a[1] for a in att], index=t, columns=cols)
slv = pd.Series([a[2] for a in att], index=t)
eq = pd.Series(cap["eq"], index=idx + pd.Timedelta(hours=4))
eqm = pd.Series(cap["eq_min"], index=idx + pd.Timedelta(hours=4))
gov = pd.Series(cap["g"], index=idx + pd.Timedelta(hours=4))
anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
out = {}
for y in range(4):
    a0, a1 = anchors[y], anchors[y + 1]
    e = eq[(eq.index > a0) & (eq.index <= a1)]
    em = eqm.reindex(e.index)
    e = e / e.iloc[0]
    em = em / eq[(eq.index > a0)].iloc[0]
    peak = np.maximum.accumulate(np.r_[1.0, e.to_numpy()])[1:]
    dd = 1 - np.minimum(e.to_numpy(), em.to_numpy()) / peak
    k = int(np.argmax(dd))
    p = int(np.argmax(e.to_numpy()[:k + 1])) if k > 0 else 0
    win = e.index[p + 1:k + 1]
    rec = {"dd_pct": round(100 * float(dd[k]), 2), "peak": str(e.index[p]), "trough": str(e.index[k]), "bars": len(win),
           "book_pnl_by_coin_pct": {c: round(100 * float(book.reindex(win)[c].sum()), 2) for c in cols},
           "sleeve_pnl_pct": round(100 * float(slv.reindex(win).sum()), 2),
           "governor_min": round(float(gov.reindex(win).min()), 3) if len(win) else None}
    # the worst single bars in the episode
    tot = book.reindex(win).sum(axis=1) + slv.reindex(win)
    rec["worst_bars"] = [(str(i), round(100 * float(v), 2), round(100 * float(slv.get(i, 0)), 2)) for i, v in tot.nsmallest(5).items()]
    out[str(a0.year)] = rec
    print(a0.year, json.dumps(rec))
Path("research/diagnostics/o1_dd_episodes/o1_dd_episodes.json").write_text(json.dumps(out, indent=1))
