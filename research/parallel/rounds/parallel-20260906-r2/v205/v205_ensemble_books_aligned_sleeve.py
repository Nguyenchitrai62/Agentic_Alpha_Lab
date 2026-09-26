"""v205: annual+quarterly retrained book ensemble (v203) with the book-aligned sleeve (v204) (registry v205).

Why: v203's 0.5 annual + 0.5 quarterly books had the better worst dev year (+47% vs +41%) but lost on the mean
criterion; v204's aligned sleeve (x1.5 on assets the books are long, x0.5 otherwise) improved both dev and the unused
last year. Under the robust criterion (from v204) the combination is the natural candidate.
Pre-registered pipelines (the only two): v204 selection (annual v151 books + aligned sleeve) = reference; ensemble books
(0.5 annual + 0.5 quarterly v151) + the same aligned sleeve. Everything else = v204 (engine_user after the v188-audit
fix). SELECTION = robust criterion (AGENTS.md). The selected pipeline's most recent year is the one-time final score.

  python research/parallel/rounds/parallel-20260906-r2/v205/v205_ensemble_books_aligned_sleeve.py
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
spec = importlib.util.spec_from_file_location("v204", HERE.parent / "v204/v204_sleeve_book_alignment.py")
v204 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v204)


def main():
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    A, B = (mem.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    mq = pd.read_parquet(eu.er.CACHE / "members_quarterly.parquet")
    Aq, Bq = (mq.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    annual, quarterly = (A + B) / 2, (Aq + Bq) / 2
    prep = eu.prepare(books154, opens)
    kw = dict(m_sl=4.0, m_sleeve_sl=5.0, sleeve=True, d_limit=0.001, win_end=239, sleeve_risk_budget=0.12, size_mult=1.5, align=(1.5, 0.5))
    out = {"version": "v205", "criterion": "robust worst-year (AGENTS.md)", "rows": {}}
    for key, bk in (("ref_v204_annual", annual), ("ensemble_annual_quarterly", 0.5 * annual + 0.5 * quarterly)):
        r = eu.simulate(bk, opens, prep, **kw)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key] = r
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "years", [(y["anchor"][:4], y["net_pct"]) for y in r["yearly"][:4]], flush=True)
        if key.startswith("ref"):
            assert abs(r["monthly_dev4"] - 5.872) < 0.002, "reference must reproduce v204"
    sel = v204.robust_select(out["rows"])
    s = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s["monthly_5y"], "monthly_last_year": s["monthly_last_year"],
                                   "losing_years": s["losing_years"], "gate_dd": s["gate_dd"], "gate_pass": s["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s["yearly"]]}
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v205_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
