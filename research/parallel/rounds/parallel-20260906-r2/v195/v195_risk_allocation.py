"""v195: risk allocation between the books and the dip sleeve (registry v195).

The sleeve (liquidation-rebound bids with stops) has a higher return per unit of risk than the books over the first
four years; the books' vol target and the sleeve's stop-risk budget are the two risk dials. Pre-registered variants (the
only ones): (books target 0.25, sleeve budget 0.08) = v193/v194 selection; (0.20, 0.12); (0.15, 0.16). Everything else as
v193 (v151 books, 10 bps book limits resting the whole bar, book SL/TP m = 4, rung stop 5 sigma_4h, TP 1 sigma_4h;
engine_user). Note the rung notional rn = s g 0.25/4/1.657 scales with the books' scale s, so the budget is what moves
the sleeve. SELECTION on the first four years (monthly_dev4, DD <= 20, no losing year among them); the selected variant's
most recent year is the one-time final score.

  python research/parallel/rounds/parallel-20260906-r2/v195/v195_risk_allocation.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("engine_user", HERE.parent / "engine_user/engine_user.py")
eu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eu)
VARIANTS = ((0.25, 0.08), (0.20, 0.12), (0.15, 0.16))


def main():
    books154, opens = eu.er.v154_books()
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    cols = list(books154.columns)
    A, B = (mem.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    v151 = (A + B) / 2
    prep = eu.prepare(books154, opens)
    out = {"version": "v195", "rows": {}}
    for tg, x in VARIANTS:
        key = f"t{tg}_x{x}"
        r = eu.simulate(v151, opens, prep, m_sl=4.0, m_sleeve_sl=5.0, sleeve=True, d_limit=0.001, win_end=239,
                        sleeve_risk_budget=x, target=tg)
        out["rows"][key] = r
        print(key, "dev4", r["monthly_dev4"], "gateDD", r["gate_dd"], "rungs", r["stats"]["rungs"], "years",
              [(y["anchor"][:4], y["net_pct"]) for y in r["yearly"][:4]], flush=True)
    ok = {k: v for k, v in out["rows"].items() if v["gate_dd"] <= 20 and all(y["net_pct"] >= 0 for y in v["yearly"][:4])}
    pool = ok or out["rows"]
    sel = max(pool, key=lambda k: pool[k]["monthly_dev4"])
    s = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s["monthly_5y"], "monthly_last_year": s["monthly_last_year"],
                                   "losing_years": s["losing_years"], "gate_dd": s["gate_dd"], "gate_pass": s["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s["yearly"]]}
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v195_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
