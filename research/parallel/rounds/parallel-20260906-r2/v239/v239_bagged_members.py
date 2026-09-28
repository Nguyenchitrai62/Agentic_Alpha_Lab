"""v239: variance reduction of the foundation models by bagging (registry v239).

Why: dev-mean gains repeatedly failed to reach the unseen year (v234, v237, v238: more features -> higher DD / lower last year), the
signature of high-variance fits. Every return model is ONE HistGradientBoostingRegressor (depth 4, lr 0.03, 400 iter, min leaf 300,
l2 1, seed 0) on all features. Bagging averages K models that each see a random subset of the features at every split - a standard
way to reduce variance without new information.
Fixed before running: BagHGB = mean of K = 5 HistGradientBoostingRegressor with the SAME hyperparameters plus max_features = 0.7 and
random_state = 0..4; it replaces the return models of v92 (long-only), v94 (long/short) and v103 (flow) inside the member builders
(module-level patch of HistGradientBoostingRegressor in those modules); the v129 vol models are unchanged. Features / targets / anchors
/ embargo exactly as the members of v236 W2 (A: 4h TradingView + per-asset whale flow; B: options + TradingView).
Everything else = v218 D2 settings (v216 G2 grid trader, sleeve budget 0.15, rung x1.75, minute-5 rule, limit orders, SL market /
TP limit, governor, aligned sleeve, Bybit fees, adverse funding).
  G1_bag_A     bagged A members (annual + quarterly), B members = T3 (as W2)
  G2_bag_all   bagged A and B members
Reference: v236_W2 (must reproduce dev4 5.774). SELECTION = robust criterion among G1, G2; the most recent year is scored once for the
selected row.

  python research/parallel/rounds/parallel-20260906-r2/v239/v239_bagged_members.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).parent
RD = HERE.parent
K, MAX_FEATURES = 5, 0.7


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class BagHGB:
    """Mean of K HistGradientBoostingRegressor with max_features < 1 and different seeds (same other hyperparameters)."""

    def __init__(self, **kw):
        self.kw = {k: v for k, v in kw.items() if k != "random_state"}

    def fit(self, X, y, **fit_kw):
        self.models = [HistGradientBoostingRegressor(**self.kw, max_features=MAX_FEATURES, random_state=s).fit(X, y, **fit_kw)
                       for s in range(K)]
        return self

    def predict(self, X):
        return np.mean([m.predict(X) for m in self.models], axis=0)


v236 = _load("v236_g", RD / "v236/v236_whale_flow.py")
v233 = _load("v233_g", RD / "v233/v233_tv_all_members.py")


def _patch(v144):
    ext = v144.v115.v114.v113
    for mod in (ext.v92, ext.v94, v144.v103):
        mod.HistGradientBoostingRegressor = BagHGB


def build_member(kind: str, quarterly: bool):
    """kind 'A': v144 + TV + per-asset flow (the W2 A members); 'B': options + TV (the T3 B members); all with bagged return models."""
    tag = f"{kind}{'q' if quarterly else 'a'}_bag"
    v202 = _load(f"v202_{tag}", RD / "v202/v202_quarterly_retrain.py")
    if kind == "B":
        v150 = _load(f"v150_{tag}", RD / "v150/v150_options_flow.py")
        v144, OPT, ofeats = v150.v144, list(v150.OPT), v150.opt_features()
    else:
        v144, OPT, ofeats = _load(f"v144_{tag}", RD / "v144/v144_deploy_v3.py"), [], None
    if quarterly:
        v202.quarterly(v144)
    _patch(v144)
    ext, v103 = v144.v115.v114.v113, v144.v103
    ext.cb_bars = v144.v115.v114.cb_bars_ext
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    b92, b103, orig_vp = ext.v92.build, v103.build, v144.v129.vol_predict
    base92 = b92()
    if kind == "A":
        xf = v236.feature_frame(ext.v92.load_asset)
    else:
        xf = v233.v231.extra_features(("tv",), ext.v92.load_asset, None)
    drop = set(OPT) | {c for c in xf.columns if c not in ("t", "sym")}
    v144.v129.vol_predict = lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in drop], anchors, emb)

    def add(p):
        if ofeats is not None:
            p = p.merge(ofeats, on="t", how="left")
        return p.merge(xf, on=["t", "sym"], how="left")
    ext.v92.build = lambda: add(base92)
    v103.build = lambda: add(b103())
    return v144.books_v142()[1]


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    C = eu.er.CACHE
    w2 = {k: pd.read_parquet(C / f) for k, f in (("A", "member_A_whale.parquet"), ("Aq", "member_Aq_whale.parquet"),
                                                  ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    bag = {}
    for name, kind, q in (("A", "A", False), ("Aq", "A", True), ("B", "B", False), ("Bq", "B", True)):
        cache = C / f"member_{name}_bag.parquet"
        if not cache.exists():
            build_member(kind, q).to_parquet(cache)
        bag[name] = pd.read_parquet(cache)
        print("member", name, "bagged cached", flush=True)
    mixes = {"v236_W2": w2, "G1_bag_A": {"A": bag["A"], "Aq": bag["Aq"], "B": w2["B"], "Bq": w2["Bq"]}, "G2_bag_all": bag}
    prep = eu.prepare(books154, opens)
    pol = v216.grid_policy(v221.B_ABS, v221.B_REL)
    out = {"version": "v239", "k": K, "max_features": MAX_FEATURES, "rows": {}, "trades": {}}
    for key, mm in mixes.items():
        m = {k: v.reindex(idx).fillna(0.0)[cols] for k, v in mm.items()}
        books = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
        ev = []
        r = eu.simulate(books, opens, prep, trade=dict(v216.GRID, policy=pol), win_start=5, events=ev, **v221.KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trades", out["trades"][key]["dev"], flush=True)
        if key == "v236_W2":
            assert abs(r["monthly_dev4"] - 5.774) < 0.002
    sel = v204.robust_select({k: out["rows"][k] for k in ("G1_bag_A", "G2_bag_all")})
    s = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s["monthly_5y"], "monthly_last_year": s["monthly_last_year"],
                                   "losing_years": s["losing_years"], "gate_dd": s["gate_dd"], "gate_pass": s["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s["yearly"]],
                                   "hidden_year_trades": out["trades"][sel]["_hidden"]}
    for k in out["trades"]:
        if k != sel:
            out["trades"][k].pop("_hidden", None)
    for k in out["rows"]:
        if k != sel:
            for fld in ("monthly_last_year", "monthly_5y"):
                out["rows"][k].pop(fld, None)
            out["rows"][k]["yearly"] = out["rows"][k]["yearly"][:4]
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v239_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
