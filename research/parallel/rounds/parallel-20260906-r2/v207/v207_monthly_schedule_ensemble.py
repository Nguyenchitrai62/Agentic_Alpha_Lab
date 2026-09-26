"""v207: add a MONTHLY retraining schedule to the annual+quarterly book ensemble (registry v207).

Why: ensembling model sets trained on different schedules improved robustness (v203 -> v205); a monthly schedule adds the
freshest models and more diversity. Fixed before running: members A (v144) and B (v151 options) rebuilt with monthly
anchors 2021-09-24 + k calendar months, k = 0..59, each model predicting only its own month (per-target cutoffs and
embargoes unchanged, relative to each anchor; same wrapping as v202), cached in
artifacts/research/engine_real/members_monthly.parquet. Pipelines (the only two): v205 selection ((A + B + Aq + Bq)/4) =
reference; equal thirds of annual, quarterly and monthly v151 books. Sleeve and rules = v205. SELECTION = robust criterion
(AGENTS.md). The selected pipeline's most recent year is the one-time final score.

  python research/parallel/rounds/parallel-20260906-r2/v207/v207_monthly_schedule_ensemble.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, RD / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


eu = _load("engine_user", "engine_user/engine_user.py")
v202 = _load("v202_m", "v202/v202_quarterly_retrain.py")
v204 = _load("v204", "v204/v204_sleeve_book_alignment.py")
M = [str(d.date()) for d in pd.date_range("2021-09-24", periods=60, freq=pd.DateOffset(months=1))]


def members_monthly(cache):
    if cache.exists():
        m = pd.read_parquet(cache)
        return m.xs("A", axis=1, level=0), m.xs("B", axis=1, level=0)
    v202.Q[:] = M
    v202.END.clear()
    v202.END.update({a: (M[i + 1] if i + 1 < len(M) else "2026-09-24") for i, a in enumerate(M)})
    A, B = v202.members_quarterly(cache)  # same builder, monthly schedule; writes the cache
    return A, B


def main():
    books154, opens = eu.er.v154_books()
    cols, idx = list(books154.columns), books154.index
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    A, B = (mem.xs(k, axis=1, level=0).reindex(idx).fillna(0.0)[cols] for k in ("A", "B"))
    mq = pd.read_parquet(eu.er.CACHE / "members_quarterly.parquet")
    Aq, Bq = (mq.xs(k, axis=1, level=0).reindex(idx).fillna(0.0)[cols] for k in ("A", "B"))
    Am, Bm = members_monthly(eu.er.CACHE / "members_monthly.parquet")
    Am, Bm = (X.reindex(idx).fillna(0.0)[cols] for X in (Am, Bm))
    annual, quarterly, monthly = (A + B) / 2, (Aq + Bq) / 2, (Am + Bm) / 2
    prep = eu.prepare(books154, opens)
    kw = dict(m_sl=4.0, m_sleeve_sl=5.0, sleeve=True, d_limit=0.001, win_end=239, sleeve_risk_budget=0.12, size_mult=1.5, align=(1.5, 0.5))
    out = {"version": "v207", "criterion": "robust worst-year (AGENTS.md)", "rows": {}}
    for key, bk in (("ref_v205", 0.5 * annual + 0.5 * quarterly), ("annual_quarterly_monthly", (annual + quarterly + monthly) / 3)):
        r = eu.simulate(bk, opens, prep, **kw)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key] = r
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "years", [(y["anchor"][:4], y["net_pct"]) for y in r["yearly"][:4]], flush=True)
        if key.startswith("ref"):
            assert abs(r["monthly_dev4"] - 5.824) < 0.002, "reference must reproduce v205"
    sel = v204.robust_select(out["rows"])
    s = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s["monthly_5y"], "monthly_last_year": s["monthly_last_year"],
                                   "losing_years": s["losing_years"], "gate_dd": s["gate_dd"], "gate_pass": s["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s["yearly"]]}
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v207_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
