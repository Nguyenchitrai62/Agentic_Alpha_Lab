"""v221: hysteresis on the grid trader's exits - open at |target| >= 5%, close only when the signal is clearly gone (registry v221).

Why: in v216/v218 about 80% of the grid trader's positions end with a limit exit because |target| dipped below the 5% opening
threshold (812 of 1016 dev trades); a signal oscillating around the threshold makes the trader close and re-open (fees, lost trend).
Traders use a wider exit band than entry band.
Fixed before running (everything = v218 D2: v216 G2 grid trader, dip sleeve budget 0.15, rung x1.75, v205 books / governor /
aligned sleeve / Bybit fees / adverse funding, minute-5 rule, limit orders, SL market / TP limit). Opening and the cancel rule of a
resting entry are unchanged (5%). In a position, with v = target along the position (negative = opposite side):
  reversal (v <= -5%) -> tighten + limit close (unchanged); v < C -> limit close; otherwise the G2 grid adjustments toward max(v, 0).
  Y1_hyst25        C = 2.5%.
  Y2_hyst10        C = 1.0%.
  Y3_hyst25_ema    C = 2.5% applied to an EMA (alpha 0.5 per 4h bar) of v per coin, so one weak bar does not close.
Reference: v218_D2 (C = 5%, i.e. no hysteresis). SELECTION = robust criterion among Y1..Y3; most recent year scored once.

  python research/parallel/rounds/parallel-20260906-r2/v221/v221_grid_hysteresis.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v216 = _load("v216", HERE.parent / "v216/v216_trade_grid.py")
eu, v204, v213 = v216.eu, v216.v204, v216.v213
KW = dict(v216.KW, sleeve_risk_budget=0.15, size_mult=1.75)
B_ABS, B_REL, COOL, THETA = 0.03, 0.40, 6, 0.05
VARIANTS = {"Y1_hyst25": (0.025, False), "Y2_hyst10": (0.010, False), "Y3_hyst25_ema": (0.025, True)}


def hyst_policy(close_th, ema):
    state = {}

    def pol(i, a, st):
        if st["pos"] == 0:
            state.pop(a, None)
            return "open"
        side, tg, w, valid = st["pos"], st["tg"], st["w"], st["valid"]
        v = tg * side
        if v <= -THETA:
            state.pop(a, None)
            return {"tighten": 1, "close": 1} if "close" in valid else "tighten"
        m = v
        if ema:
            prev = state.get(a)
            m = v if prev is None else 0.5 * prev + 0.5 * v
            state[a] = m
        if m < close_th:
            return "close" if "close" in valid else "hold"
        if st["since_adj"] < COOL:
            return "hold"
        tgt = max(v, 0.0)
        band = max(B_ABS, B_REL * tgt)
        diff = tgt - w
        if diff > band and "add" in valid:
            return {"add": diff}
        if -diff > band and "reduce" in valid and w > 0:
            return {"reduce": min(1.0, -diff / w)}
        return "hold"
    return pol


def main():
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    A, B = (mem.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    mq = pd.read_parquet(eu.er.CACHE / "members_quarterly.parquet")
    Aq, Bq = (mq.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    books = 0.5 * (A + B) / 2 + 0.5 * (Aq + Bq) / 2
    prep = eu.prepare(books154, opens)
    out = {"version": "v221", "variants": VARIANTS, "rows": {}, "trades": {}}
    runs = [("v218_D2", v216.grid_policy(B_ABS, B_REL))] + [(k, hyst_policy(*v)) for k, v in VARIANTS.items()]
    for key, pol in runs:
        ev = []
        r = eu.simulate(books, opens, prep, trade=dict(v216.GRID, policy=pol), win_start=5, events=ev, **KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trades", out["trades"][key]["dev"], flush=True)
        if key == "v218_D2":
            assert abs(r["monthly_dev4"] - 5.261) < 0.002
    sel = v204.robust_select({k: out["rows"][k] for k in VARIANTS})
    s = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s["monthly_5y"], "monthly_last_year": s["monthly_last_year"],
                                   "losing_years": s["losing_years"], "gate_dd": s["gate_dd"], "gate_pass": s["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s["yearly"]],
                                   "hidden_year_trades": out["trades"][sel]["_hidden"]}
    for k in out["trades"]:
        if k != sel:
            out["trades"][k].pop("_hidden", None)
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v221_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
