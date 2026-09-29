"""Diagnostic (first four walk-forward years only, not registered): would a BTC short hedge on ALT dip-sleeve fills keep the edge and cut
the tail? For every ETH / SOL / BNB / XRP dip-rung fill of the O1 B18 run, hedged return = rung net return - beta * BTC return from the
fill minute to the exit minute - hedge costs (taker 0.055% in and out). beta = 1 and beta = causal 30-day beta of 1h returns (up to the
hour before the fill). Reports per dev year: n, mean, q01, stop share, weighted sum and the worst bar (sum of weighted fill results in one
4h bar), unhedged vs hedged; plus the share of fills where BTC itself was flushing (BTC 1m return from the bar open < -1.5 sigma_4h).
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
ib = _load("ib", RD / "v252/intrabar_flow.py")
eu, v216 = v221.eu, v221.v216
books154, opens = eu.er.v154_books()
cols, idx = list(books154.columns), books154.index
C = eu.er.CACHE
m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
    ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
books = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
prep = eu.prepare(books154, opens)
ev = []
eu.simulate(books, opens, prep, trade=dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL)), win_start=5, events=ev,
            **dict(v221.KW, sleeve_risk_budget=0.18))
anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
rows, last = [], None
for e in ev:
    if e["kind"] == "rung_fill":
        last = e
    elif e["kind"] in ("rung_tp", "rung_sl", "rung_timeout") and last is not None:
        rows.append(dict(t=last["t"], x=e["t"], sym=last["symbol"], w=last["weight"], ret=e["ret"], kind=e["kind"]))
        last = None
d = pd.DataFrame(rows)
d = d[(d.t >= anchors[0]) & (d.t < anchors[4])].reset_index(drop=True)
btc = ib._closes("BTCUSDT")
btc = btc[btc.index < anchors[4]]
h1 = btc.resample("1h").last().pct_change()
alts = {s: ib._closes(s) for s in cols if s != "BTCUSDT"}
alts = {s: v[v.index < anchors[4]].resample("1h").last().pct_change() for s, v in alts.items()}


def px(series, t):
    return float(series.asof(t))


d = d[d.sym != "BTCUSDT"].copy()
# the fill happens inside minute t (limit trade-through); the hedge is sold at the close of that minute, bought back at the exit minute close
d["btc_ret"] = [px(btc, x) / px(btc, t) - 1 for t, x in zip(d.t, d.x)]
betas = []
for t, s in zip(d.t, d.sym):
    end = t.floor("1h") - pd.Timedelta(hours=1)
    a, b = alts[s].loc[end - pd.Timedelta(days=30):end], h1.loc[end - pd.Timedelta(days=30):end]
    j = pd.concat([a, b], axis=1).dropna()
    betas.append(float(np.cov(j.iloc[:, 0], j.iloc[:, 1])[0, 1] / j.iloc[:, 1].var()) if len(j) > 100 else 1.0)
d["beta"] = betas
cost = 2 * 0.00055
d["h1"] = d.ret - d.btc_ret - cost
d["hb"] = d.ret - d.beta * d.btc_ret - d.beta * cost
d["bar"] = d.t.dt.floor("4h")
d["year"] = [max(j for j, a0 in enumerate(anchors) if t >= a0) for t in d.t]
out = {}
for y in range(4):
    g = d[d.year == y]
    row = {"n": len(g), "stop_share": round(float((g.kind == "rung_sl").mean()), 3), "mean_beta": round(float(g.beta.mean()), 2)}
    for k in ("ret", "h1", "hb"):
        row[k] = dict(mean_pct=round(100 * g[k].mean(), 3), q01_pct=round(100 * g[k].quantile(0.01), 2),
                      wsum_pct=round(100 * (g.w * g[k]).sum(), 2), worst_bar_pct=round(100 * float((g.w * g[k]).groupby(g.bar).sum().min()), 2))
    out[str(anchors[y].year)] = row
    print(anchors[y].year, json.dumps(row))
Path("research/diagnostics/sleeve_hedge/sleeve_hedge_dev.json").write_text(json.dumps(out, indent=1))
