"""v202: quarterly walk-forward retraining of the book models (registry v202).

Why: the models are retrained once a year (at each anchor); in live use they would be refreshed regularly on the newest
data, which should adapt faster to regime changes. Evaluating quarterly retraining is both more realistic and a fair
comparison across all years (it changes the dev years too).
Fixed before running:
- Quarterly anchors 2021-09-24, 2021-12-24, ..., 2026-06-24 (20 anchors, calendar months +3); each model predicts only
  its own quarter [anchor, next anchor) (the last one until 2026-09-24). Per-target cutoffs/embargoes unchanged
  (relative to each anchor). Implemented by wrapping the audited train_predict/vol_predict functions of fresh module
  instances (v92 LO, v94 LS, v103 flow, v129 vol forecast); members A (v144 books) and B (v151 options member) rebuilt.
- Pipelines (the only two): v151 books with ANNUAL retraining (reference = v197) and v151 books with QUARTERLY
  retraining, both with the v197 sleeve and rules (engine_user after the v188-audit fix).
- SELECTION on the first four years (monthly_dev4, gate DD <= 20, no losing year among them); the selected pipeline's
  most recent year is the one-time final score. Quarterly member books are cached in
  artifacts/research/engine_real/members_quarterly.parquet.

  python research/parallel/rounds/parallel-20260906-r2/v202/v202_quarterly_retrain.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
Q = [str(d.date()) for d in pd.date_range("2021-09-24", periods=20, freq=pd.DateOffset(months=3))]
END = {a: (Q[i + 1] if i + 1 < len(Q) else "2026-09-24") for i, a in enumerate(Q)}


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, RD / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cut(df, a):
    A, E = pd.Timestamp(a, tz="UTC"), pd.Timestamp(END[str(pd.Timestamp(a).date())], tz="UTC")
    return df[(df.t >= A) & (df.t < E)]


def quarterly(v144):
    ext, v103, v129 = v144.v115.v114.v113, v144.v103, v144.v129
    o92, o94, o103, ovp = ext.v92.train_predict, ext.v94.train_predict, v103.train_predict, v129.vol_predict

    def tp92(panel, a):
        r = o92(panel, a)
        return (_cut(r[0], a),) + tuple(r[1:])

    def tp94(panel, a, f):
        r = o94(panel, a, f)
        return (_cut(r[0], a),) + tuple(r[1:])

    def tp103(panel, a, f):
        r = o103(panel, a, f)
        return (_cut(r[0], a),) + tuple(r[1:])

    def vp(panel, fs, anchors, emb):
        return pd.concat([_cut(ovp(panel, fs, [a], emb)[0], a) for a in anchors], ignore_index=True), {}

    ext.v92.train_predict, ext.v94.train_predict, v103.train_predict, v129.vol_predict = tp92, tp94, tp103, vp
    ext.v92.ANCHORS = tuple(Q)
    return v144


def members_quarterly(cache):
    if cache.exists():
        m = pd.read_parquet(cache)
        return m.xs("A", axis=1, level=0), m.xs("B", axis=1, level=0)
    v144a = quarterly(_load("v144_q_a", "v144/v144_deploy_v3.py"))
    _, A = v144a.books_v142()
    print("member A rebuilt (quarterly)", A.shape, flush=True)
    v150 = _load("v150_q", "v150/v150_options_flow.py")
    v144b = quarterly(v150.v144)
    OPT, feats = v150.OPT, v150.opt_features()
    ext, v103 = v144b.v115.v114.v113, v144b.v103
    b92, b103, orig_vp = ext.v92.build, v103.build, v144b.v129.vol_predict
    v144b.v129.vol_predict = lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in OPT], anchors, emb)
    ext.cb_bars = v144b.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    ext.v92.build = lambda: b92().merge(feats, on="t", how="left")
    v103.build = lambda: b103().merge(feats, on="t", how="left")
    _, B = v144b.books_v142()
    print("member B rebuilt (quarterly)", B.shape, flush=True)
    idx = A.index.union(B.index)
    out = {"A": A.reindex(idx).fillna(0.0), "B": B.reindex(idx).fillna(0.0)}
    pd.concat(out, axis=1).to_parquet(cache)
    return out["A"], out["B"]


def main():
    spec = importlib.util.spec_from_file_location("engine_user", RD / "engine_user/engine_user.py")
    eu = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(eu)
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    A, B = (mem.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    Aq, Bq = members_quarterly(eu.er.CACHE / "members_quarterly.parquet")
    Aq, Bq = (X.reindex(books154.index).fillna(0.0)[cols] for X in (Aq, Bq))
    prep = eu.prepare(books154, opens)
    kw = dict(m_sl=4.0, m_sleeve_sl=5.0, sleeve=True, d_limit=0.001, win_end=239, sleeve_risk_budget=0.12, size_mult=1.5)
    out = {"version": "v202", "anchors_quarterly": Q, "rows": {}}
    for key, bk in (("ref_annual_v151", (A + B) / 2), ("quarterly_v151", (Aq + Bq) / 2)):
        r = eu.simulate(bk, opens, prep, **kw)
        out["rows"][key] = r
        print(key, "dev4", r["monthly_dev4"], "gateDD", r["gate_dd"], "years", [(y["anchor"][:4], y["net_pct"]) for y in r["yearly"][:4]], flush=True)
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
    (HERE / "v202_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
