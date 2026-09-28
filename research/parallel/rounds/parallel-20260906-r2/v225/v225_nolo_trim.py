"""v225: the no-long-only foundation (v224 F3) with a small risk trim to fit DD <= 20 (registry v225).

Why: v224 F3 (member book = 0.30 ls/0.25 + 0.70 fl/0.5, i.e. no long-only 7d component) had the best worst dev year of all trade-mode
pipelines (2.282 vs D2 2.182) and a higher trade win rate (52.6%), but gate DD 20.89. LABEL: F3's most recent year was scored once in
v224 (4.336); this version therefore needs the prospective log as clean evidence, whatever its result.
Fixed before running (everything else = v218 D2 on the F3 books):
  T1_book95     book positions x 0.95 (trade["book_mult"]).
  T2_book90     book positions x 0.90.
  T3_sleeve14   books x 1.0, dip-sleeve stop-risk budget 0.14 (instead of 0.15).
References: v218_D2 (ref mix), v224_F3 (x1.0). SELECTION = robust criterion among T1..T3; the most recent year is scored once for the
selected row.

  python research/parallel/rounds/parallel-20260906-r2/v225/v225_nolo_trim.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
CACHE = Path("artifacts/research/engine_real")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v221 = _load("v221", HERE.parent / "v221/v221_grid_hysteresis.py")
v216, eu, v204, v213 = v221.v216, v221.eu, v221.v204, v221.v216.v213
KW = v221.KW
MIXES = {"ref_mix": (0.25, 0.25, 0.50), "F3": (0.00, 0.30, 0.70)}
RUNS = {"v218_D2": ("ref_mix", 1.0, 0.15), "v224_F3": ("F3", 1.0, 0.15), "T1_book95": ("F3", 0.95, 0.15), "T2_book90": ("F3", 0.90, 0.15),
        "T3_sleeve14": ("F3", 1.0, 0.14)}


def member(name, mix, index, cols):
    c = pd.read_parquet(CACHE / f"components_{name}.parquet")
    lo, ls, fl = (c.xs(k, axis=1, level=0).reindex(index).fillna(0.0)[cols] for k in ("lo", "ls", "fl"))
    return mix[0] * lo / 0.25 + mix[1] * ls / 0.25 + mix[2] * fl / 0.5


def main():
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    prep = eu.prepare(books154, opens)
    pol = v216.grid_policy(v221.B_ABS, v221.B_REL)
    out = {"version": "v225", "mixes": MIXES, "runs": RUNS, "rows": {}, "trades": {}}
    books_by = {}
    for mk, mix in MIXES.items():
        A, B, Aq, Bq = (member(n, mix, idx, cols) for n in ("A_annual", "B_annual", "A_quarterly", "B_quarterly"))
        books_by[mk] = 0.5 * (A + B) / 2 + 0.5 * (Aq + Bq) / 2
    for key, (mk, mult, budget) in RUNS.items():
        ev = []
        r = eu.simulate(books_by[mk], opens, prep, trade=dict(v216.GRID, policy=pol, book_mult=mult), win_start=5, events=ev,
                        **dict(KW, sleeve_risk_budget=budget))
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trades", out["trades"][key]["dev"], flush=True)
        if key == "v218_D2":
            assert abs(r["monthly_dev4"] - 5.261) < 0.002
        if key == "v224_F3":
            assert abs(r["monthly_dev4"] - 5.093) < 0.002
    cands = ("T1_book95", "T2_book90", "T3_sleeve14")
    sel = v204.robust_select({k: out["rows"][k] for k in cands})
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
    (HERE / "v225_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
