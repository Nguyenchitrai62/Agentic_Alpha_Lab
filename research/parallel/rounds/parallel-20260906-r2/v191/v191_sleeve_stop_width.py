"""v191: stop-loss width of the dip-sleeve rungs under the user's rules (registry v191).

Every sleeve rung must carry a market stop (user rule). v188 used a stop at L(1 - 2 sigma_4h): 424 of ~2550 rungs were
stopped, often just before the rebound the sleeve exists to capture. Pre-registered variants (the only ones for this
direction): rung stop at 2 (reference, = v189 selected pipeline), 3 and 5 sigma_4h below the fill; TP unchanged at
L(1 + sigma_4h). Pipeline: v151 books (v189 selection) + sleeve, book SL/TP m = 4, engine_user.
SELECTION on the first four years (monthly_dev4, DD <= 20, no losing year among them); the selected variant's most
recent year is the one-time final score.

  python research/parallel/rounds/parallel-20260906-r2/v191/v191_sleeve_stop_width.py
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
VARIANTS = (2.0, 3.0, 5.0)


def main():
    books154, opens = eu.er.v154_books()
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    cols = list(books154.columns)
    A, B = (mem.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    v151 = (A + B) / 2
    prep = eu.prepare(books154, opens)
    out = {"version": "v191", "rows": {}}
    for m in VARIANTS:
        r = eu.simulate(v151, opens, prep, m_sl=4.0, m_sleeve_sl=m, sleeve=True)
        out["rows"][str(m)] = r
        print("sleeve_sl", m, "dev4", r["monthly_dev4"], "gateDD", r["gate_dd"], "rung stops/tps", r["stats"]["rung_stops"], r["stats"]["rung_tps"], flush=True)
    ok = {k: v for k, v in out["rows"].items() if v["gate_dd"] <= 20 and all(y["net_pct"] >= 0 for y in v["yearly"][:4])}
    pool = ok or out["rows"]
    sel = max(pool, key=lambda k: pool[k]["monthly_dev4"])
    s = out["rows"][sel]
    out["selected"] = float(sel)
    out["final_score_selected"] = {"monthly_5y": s["monthly_5y"], "monthly_last_year": s["monthly_last_year"],
                                   "losing_years": s["losing_years"], "gate_dd": s["gate_dd"], "gate_pass": s["gate_pass"]}
    print("SELECTED sleeve_sl", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v191_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
