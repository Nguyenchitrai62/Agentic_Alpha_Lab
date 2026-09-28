"""v226: more foundation members for the executable trade mode - Coinbase-premium member D and monthly retraining (registry v226).

Why: v206 (member D) and v207 (monthly schedule) were rejected for the CONTINUOUS book (DD 20.49 / 20.68); the trade mode (v218 D2)
has a different risk structure (limit exits, grid adjustments, no churn) and more ensemble diversity may smooth its signal crossings.
Their most recent years were never reported (the reference was selected both times), so this is a clean test.
Fixed before running (everything else = v218 D2: v216 G2 grid trader, sleeve budget 0.15, rung x1.75, minute-5 rule, limits, SL market /
TP limit, governor, aligned sleeve, Bybit fees, adverse funding). Member books from the audited caches
(artifacts/research/engine_real: members_v154 A/B/D annual, members_quarterly A/B, members_quarterly_D, members_monthly A/B):
  v218_D2       mean of {A, B} x {annual, quarterly} (reference, must reproduce 5.261).
  M1_with_D     mean of {A, B, D} x {annual, quarterly}.
  M2_monthly    mean of {A, B} x {annual, quarterly, monthly}.
  M3_D_monthly  mean of {A, B} x {annual, quarterly, monthly} and D x {annual, quarterly} (10 model sets, equal weights).
SELECTION = robust criterion among M1..M3; the most recent year is scored once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v226/v226_trade_members.py
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


def main():
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    f = lambda X: X.reindex(idx).fillna(0.0)[cols]
    mem = pd.read_parquet(CACHE / "members_v154.parquet")
    mq = pd.read_parquet(CACHE / "members_quarterly.parquet")
    mm = pd.read_parquet(CACHE / "members_monthly.parquet")
    A, B, D = (f(mem.xs(k, axis=1, level=0)) for k in ("A", "B", "D"))
    Aq, Bq = (f(mq.xs(k, axis=1, level=0)) for k in ("A", "B"))
    Dq = f(pd.read_parquet(CACHE / "members_quarterly_D.parquet"))
    Am, Bm = (f(mm.xs(k, axis=1, level=0)) for k in ("A", "B"))
    sets = {"v218_D2": [A, B, Aq, Bq], "M1_with_D": [A, B, D, Aq, Bq, Dq], "M2_monthly": [A, B, Aq, Bq, Am, Bm],
            "M3_D_monthly": [A, B, Aq, Bq, Am, Bm, D, Dq]}
    prep = eu.prepare(books154, opens)
    pol = v216.grid_policy(v221.B_ABS, v221.B_REL)
    out = {"version": "v226", "rows": {}, "trades": {}}
    for key, ms in sets.items():
        books = sum(ms) / len(ms)
        ev = []
        r = eu.simulate(books, opens, prep, trade=dict(v216.GRID, policy=pol), win_start=5, events=ev, **KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trades", out["trades"][key]["dev"], flush=True)
        if key == "v218_D2":
            assert abs(r["monthly_dev4"] - 5.261) < 0.002
    cands = ("M1_with_D", "M2_monthly", "M3_D_monthly")
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
    (HERE / "v226_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
