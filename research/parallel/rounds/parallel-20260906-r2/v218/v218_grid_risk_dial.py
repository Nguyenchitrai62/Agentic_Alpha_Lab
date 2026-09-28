"""v218: spend the unused DD budget of the v216 grid trader - book size vs dip-sleeve budget (registry v218).

Why: v216 G2 (dev4 4.836, worst year 1.649, DD 18.01, no losing year) leaves ~2 points of the 20% DD budget unused; learned
parameters (v217) did not transfer. A risk dial is chosen a priori and selected on the first four years only.
Fixed before running: v216 G2 policy and settings unchanged (engine_user trade mode, minute-5 rule, limit entries/adjustments/exits,
SL 4 sigma_d market, TP 8 sigma_d limit, break-even +2 sigma_d, v205 books / governor / aligned dip sleeve / Bybit fees / adverse
funding). The dip sleeve (corr ~0.04 with the books) is an independent alpha, so the budget may pay more there:
  D1_book110   book positions x 1.10 (trade["book_mult"]); sleeve unchanged.
  D2_sleeve    sleeve stop-risk budget 0.12 -> 0.15 and rung size x 1.5 -> x 1.75; books unchanged.
  D3_mix       book x 1.05, sleeve budget 0.135, rung size x 1.6.
Reference: grid_G2 (M = 1). SELECTION = robust criterion (DD <= 20, no losing dev year, then the best worst dev year, ties -> mean)
among D1..D3; the most recent year is scored once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v218/v218_grid_risk_dial.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v216 = _load("v216", HERE.parent / "v216/v216_trade_grid.py")
eu, v204, v213 = v216.eu, v216.v204, v216.v213
VARIANTS = {"D1_book110": (1.10, 0.12, 1.5), "D2_sleeve": (1.0, 0.15, 1.75), "D3_mix": (1.05, 0.135, 1.6)}


def main():
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    A, B = (mem.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    mq = pd.read_parquet(eu.er.CACHE / "members_quarterly.parquet")
    Aq, Bq = (mq.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    books = 0.5 * (A + B) / 2 + 0.5 * (Aq + Bq) / 2
    prep = eu.prepare(books154, opens)
    pol = v216.grid_policy(*v216.VARIANTS["G2_medium"])
    out = {"version": "v218", "variants": VARIANTS, "rows": {}, "trades": {}}
    for key, (mult, budget, rung) in [("grid_G2", (1.0, 0.12, 1.5))] + list(VARIANTS.items()):
        ev = []
        kw = dict(v216.KW, sleeve_risk_budget=budget, size_mult=rung)
        r = eu.simulate(books, opens, prep, trade=dict(v216.GRID, policy=pol, book_mult=mult), win_start=5, events=ev, **kw)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trades", out["trades"][key]["dev"], flush=True)
        if key == "grid_G2":
            assert abs(r["monthly_dev4"] - 4.836) < 0.002
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
    (HERE / "v218_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
