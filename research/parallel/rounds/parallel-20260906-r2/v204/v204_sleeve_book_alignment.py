"""v204: dip-sleeve rung size aligned with the books' direction (registry v204).

Why: buying liquidation dips in assets the books are long (trend-aligned) should rebound more reliably than buying dips
in assets the books are short or flat. Pre-registered variants (the only ones): rung size multiplier (book long, book
short/flat) = (1, 1) reference = v197, (1.5, 0.5), (2, 0). The book direction is the sign of the target book weight at
the decision (known). Everything else = v197 (engine_user after the v188-audit fix); the stop-risk budget uses each
rung's own size.
SELECTION = robust criterion (AGENTS.md, from v204): among variants with DD <= 20% and no losing year in the first four
years, prefer first-four-year mean >= 5%/month if any, then the highest worst-year monthly return of the first four
years (ties -> higher mean). The selected variant's most recent year is the one-time final score.

  python research/parallel/rounds/parallel-20260906-r2/v204/v204_sleeve_book_alignment.py
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
VARIANTS = (("ref_1_1", None), ("align_1.5_0.5", (1.5, 0.5)), ("align_2_0", (2.0, 0.0)))


def worst_month(r):
    return min((1 + y["net_pct"] / 100) ** (1 / 12) - 1 for y in r["yearly"][:4]) * 100


def robust_select(rows):
    ok = {k: v for k, v in rows.items() if v["gate_dd"] <= 20 and all(y["net_pct"] >= 0 for y in v["yearly"][:4])}
    pool = ok or rows
    five = {k: v for k, v in pool.items() if v["monthly_dev4"] >= 5}
    pool = five or pool
    return max(pool, key=lambda k: (round(worst_month(pool[k]), 4), pool[k]["monthly_dev4"]))


def main():
    books154, opens = eu.er.v154_books()
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    cols = list(books154.columns)
    A, B = (mem.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    v151 = (A + B) / 2
    prep = eu.prepare(books154, opens)
    kw = dict(m_sl=4.0, m_sleeve_sl=5.0, sleeve=True, d_limit=0.001, win_end=239, sleeve_risk_budget=0.12, size_mult=1.5)
    out = {"version": "v204", "criterion": "robust worst-year (AGENTS.md)", "rows": {}}
    for key, al in VARIANTS:
        r = eu.simulate(v151, opens, prep, align=al, **kw)
        r["worst_dev_month_pct"] = round(worst_month(r), 3)
        out["rows"][key] = r
        print(key, "dev4", r["monthly_dev4"], "worst dev year %/month", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "rungs", r["stats"]["rungs"], "years", [(y["anchor"][:4], y["net_pct"]) for y in r["yearly"][:4]], flush=True)
        if key.startswith("ref"):
            assert abs(r["monthly_dev4"] - 5.562) < 0.002 and abs(r["gate_dd"] - 19.72) < 0.02, "reference must reproduce v197"
    sel = robust_select(out["rows"])
    s = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s["monthly_5y"], "monthly_last_year": s["monthly_last_year"],
                                   "losing_years": s["losing_years"], "gate_dd": s["gate_dd"], "gate_pass": s["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s["yearly"]]}
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v204_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
