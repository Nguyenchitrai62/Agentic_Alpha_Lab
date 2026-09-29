"""Diagnostic (first four walk-forward years only, not registered): what if a dip rung that is still open at the 4h bar end were held
for a fixed time from its fill instead of being sold at the next bar's open? Base = v269 M1 rules (5m-close stop at 4 sigma, 8-sigma native
backstop, TP 1 sigma limit). For every rung that TIMED OUT in the M1 run, the continuation into the next holding bar is simulated with the
same rules until the fill + H minutes (H = 240 / 480), exit at that minute's open (taker). Reports per dev year the mean / q01 of
(continued net - timeout net), the share improved, and the split by how late in the bar the rung filled.
"""
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
Cc = eu.er.CACHE
m = {k: pd.read_parquet(Cc / f).reindex(idx).fillna(0.0)[cols] for k, f in (
    ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
books = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
prep = eu.prepare(books154, opens)
ev = []
eu.simulate(books, opens, prep, trade=dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL)), win_start=5, events=ev,
            **dict(v221.KW, sleeve_risk_budget=0.18, sleeve_stop_mode="close5", sleeve_backstop=8.0, m_sleeve_sl=4.0))
C, O, H, L, sig4 = prep["C"], prep["O"], prep["H"], prep["L"], prep["sig4"]
t_hold = idx + pd.Timedelta(hours=4)
anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
MK, TK = eu.MAKER, eu.TAKER
rows, last = [], None
for e in ev:
    if e["kind"] == "rung_fill":
        last = e
    elif e["kind"] in ("rung_tp", "rung_sl", "rung_timeout") and last is not None:
        if e["kind"] == "rung_timeout":
            t0 = last["t"].floor("4h")
            i = int(np.searchsorted(t_hold, t0))
            f = int((last["t"] - t0).total_seconds() // 60)
            a = cols.index(last["symbol"])
            if t_hold[i] >= anchors[0] and t_hold[i] < anchors[4] and i + 1 < len(idx) and t_hold[i + 1] == t0 + pd.Timedelta(hours=4):
                lv, sg = float(last["price"]), float(sig4[i][a])
                tp, sl, bs = lv * (1 + sg), lv * (1 - 4 * sg), lv * (1 - 8 * sg)
                res = {}
                for Hm in (240, 480):
                    end = f + Hm - 240  # minutes into the next bar (the first bar ends at 240)
                    j = i + 1
                    ret = None
                    for k in range(0, min(end, 240)):
                        if L[j, k, a] <= bs:
                            ret = min(bs, O[j, k, a]) / lv - 1 - MK - TK
                            break
                        if (k + 1) % 5 == 0 and C[j, k, a] <= sl:
                            px = O[j, k + 1, a] if k + 1 < 240 else O[j, 239, a]
                            ret = px / lv - 1 - MK - TK
                            break
                        if H[j, k, a] > tp:
                            ret = tp / lv - 1 - 2 * MK
                            break
                    if ret is None:
                        kk = min(end, 239)
                        ret = O[j, kk, a] / lv - 1 - MK - TK
                    res[Hm] = float(ret)
                rows.append(dict(year=max(jj for jj, a0 in enumerate(anchors) if t_hold[i] >= a0), f=f, base=float(e["ret"]),
                                 w=float(last["weight"]), h240=res[240], h480=res[480]))
        last = None
d = pd.DataFrame(rows)
out = {}
for y in range(4):
    g = d[d.year == y]
    out[str(anchors[y].year)] = {"n": len(g), **{f"gain_{h}": dict(mean_pct=round(100 * (g[f"h{h}"] - g.base).mean(), 3),
                                                              q01_pct=round(100 * (g[f"h{h}"] - g.base).quantile(0.01), 2),
                                                              share_better=round(float((g[f"h{h}"] > g.base).mean()), 3),
                                                              wsum_pct=round(100 * (g.w * (g[f"h{h}"] - g.base)).sum(), 2)) for h in (240, 480)}}
    print(anchors[y].year, json.dumps(out[str(anchors[y].year)]))
late = d.f >= 180
for lab, g in (("filled_minute_lt180", d[~late]), ("filled_minute_ge180", d[late])):
    print(lab, "n", len(g), "gain240 mean %", round(100 * (g.h240 - g.base).mean(), 3), "gain480 mean %", round(100 * (g.h480 - g.base).mean(), 3))
Path("research/diagnostics/dip_carry/dip_carry_dev.json").write_text(json.dumps(out, indent=1))
