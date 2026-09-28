"""v219: shift risk from the books to the dip sleeve in the grid trader (registry v219).

Why: v218 showed that the independent dip-sleeve alpha converts DD budget into return better than a larger book (D2 sleeve budget
0.15 + rung x1.75: dev4 5.261, worst year 2.182, DD 19.09, vs book x1.10: 4.741 / 0.992). Next: move risk further from the books to
the sleeve while keeping DD <= 20.
Fixed before running (v216 G2 grid trader and every other v216 setting unchanged; book size x M via trade["book_mult"]; sleeve
stop-risk budget B and rung size x R):
  H1_book90   M 0.90, B 0.18, R 2.00
  H2_book100  M 1.00, B 0.18, R 2.00
  H3_book80   M 0.80, B 0.21, R 2.25
References: grid_G2, v218_D2 (M 1.0, B 0.15, R 1.75). SELECTION = robust criterion among H1..H3; the most recent year is scored once
for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v219/v219_sleeve_shift.py
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
VARIANTS = {"H1_book90": (0.90, 0.18, 2.0), "H2_book100": (1.0, 0.18, 2.0), "H3_book80": (0.80, 0.21, 2.25)}


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
    out = {"version": "v219", "variants": VARIANTS, "rows": {}, "trades": {}}
    for key, (mult, budget, rung) in [("grid_G2", (1.0, 0.12, 1.5)), ("v218_D2", (1.0, 0.15, 1.75))] + list(VARIANTS.items()):
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
    (HERE / "v219_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
