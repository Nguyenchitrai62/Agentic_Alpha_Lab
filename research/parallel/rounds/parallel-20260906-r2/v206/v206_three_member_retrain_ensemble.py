"""v206: add the Coinbase-premium member D to the annual+quarterly book ensemble (registry v206).

Why: ensembling helped robustness twice (v203 schedules, v205 with the aligned sleeve); member D (v154's Coinbase premium
model set) adds a third information source. Fixed before running: member D rebuilt with the v202 quarterly schedule
(cached in artifacts/research/engine_real/members_quarterly_D.parquet); books = mean over {A, B, D} x {annual,
quarterly} (six equally weighted model sets). Pipelines (the only two): v205 selection (A, B x annual, quarterly) =
reference; the three-member ensemble. Sleeve and rules = v205 (aligned sleeve x1.5 / x0.5, engine_user after the
v188-audit fix). SELECTION = robust criterion (AGENTS.md). The selected pipeline's most recent year is the one-time
final score.

  python research/parallel/rounds/parallel-20260906-r2/v206/v206_three_member_retrain_ensemble.py
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
v202 = _load("v202", "v202/v202_quarterly_retrain.py")
v204 = _load("v204", "v204/v204_sleeve_book_alignment.py")


def member_d_quarterly(cache):
    if cache.exists():
        return pd.read_parquet(cache)
    v144 = v202.quarterly(_load("v144_q_d", "v144/v144_deploy_v3.py"))
    v111 = _load("v111_q_d", "v111/v111_coinbase_premium.py")
    cbf = v111.add_cb(v144.v103.build()[["t", "sym"]]).drop(columns="sym").drop_duplicates("t")
    ext, v103 = v144.v115.v114.v113, v144.v103
    b92, b103, orig_vp = ext.v92.build, v103.build, v144.v129.vol_predict
    v144.v129.vol_predict = lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in v111.CB], anchors, emb)
    ext.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    ext.v92.build = lambda: b92().merge(cbf, on="t", how="left")
    v103.build = lambda: b103().merge(cbf, on="t", how="left")
    _, D = v144.books_v142()
    D.to_parquet(cache)
    print("member D rebuilt (quarterly)", D.shape, flush=True)
    return D


def main():
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    A, B, D = (mem.xs(k, axis=1, level=0).reindex(idx).fillna(0.0)[cols] for k in ("A", "B", "D"))
    mq = pd.read_parquet(eu.er.CACHE / "members_quarterly.parquet")
    Aq, Bq = (mq.xs(k, axis=1, level=0).reindex(idx).fillna(0.0)[cols] for k in ("A", "B"))
    Dq = member_d_quarterly(eu.er.CACHE / "members_quarterly_D.parquet").reindex(idx).fillna(0.0)[cols]
    prep = eu.prepare(books154, opens)
    kw = dict(m_sl=4.0, m_sleeve_sl=5.0, sleeve=True, d_limit=0.001, win_end=239, sleeve_risk_budget=0.12, size_mult=1.5, align=(1.5, 0.5))
    out = {"version": "v206", "criterion": "robust worst-year (AGENTS.md)", "rows": {}}
    for key, bk in (("ref_v205_AB", (A + B + Aq + Bq) / 4), ("ABD_annual_quarterly", (A + B + D + Aq + Bq + Dq) / 6)):
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
    (HERE / "v206_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
