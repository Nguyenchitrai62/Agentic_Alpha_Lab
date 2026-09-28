"""v222: several executable trader bots on separate sub-accounts (no rebalancing) - an ensemble of trade styles (registry v222).

Why: the grid trader D2 (v218; dev4 5.261, worst 2.182, DD 19.09) is strong in the chop year 2022 (+39.9%) and weaker in the trend
year 2023 (+140%), while the hysteresis trader Y3 (v221) and the hold-through trader S3 (v212 rules) are the opposite (2022 +22% /
+11%, 2023 +158% / +203%). Running them as separate bots on sub-accounts is fully executable and diversifies their path.
Fixed before running: each sub-account k gets a fixed share w_k of the capital at the start and is simulated by engine_user on its own
(own governor, own compounding, minimum notional at w_k x 10k USDT); all bots use the D2 sleeve settings (budget 0.15, rung x1.75), the
minute-5 rule, limit entries/adjustments/exits, SL market / TP limit, v205 books, Bybit fees, adverse funding. The account equity is
the sum of the sub-account equities (the 1m-marked low of the sum is bounded by the sum of the lows, used conservatively).
  K1_D2_Y3       50% D2 + 50% Y3 (v221 hysteresis, EMA of the signal, close < 2.5%).
  K2_D2_S3       50% D2 + 50% S3 (v212 rules: one limit add at 1.5x in profit, one 50% limit reduce, tighten on reversal).
  K3_D2_Y3_S3    1/3 each.
Reference: v218_D2 (100% D2). SELECTION = robust criterion among K1..K3; the most recent year is scored once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v222/v222_subaccount_ensemble.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v221 = _load("v221", HERE.parent / "v221/v221_grid_hysteresis.py")
v216, eu, v204 = v221.v216, v221.eu, v221.v204
v215 = _load("v215", HERE.parent / "v215/v215_policy_improvement.py")
KW = v221.KW
POLICIES = {"D2": lambda: v216.grid_policy(v221.B_ABS, v221.B_REL), "Y3": lambda: v221.hyst_policy(0.025, True),
            "S3": lambda: v215.rule_s3}
VARIANTS = {"K1_D2_Y3": {"D2": 0.5, "Y3": 0.5}, "K2_D2_S3": {"D2": 0.5, "S3": 0.5}, "K3_D2_Y3_S3": {"D2": 1 / 3, "Y3": 1 / 3, "S3": 1 / 3}}


def main():
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    A, B = (mem.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    mq = pd.read_parquet(eu.er.CACHE / "members_quarterly.parquet")
    Aq, Bq = (mq.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    books = 0.5 * (A + B) / 2 + 0.5 * (Aq + Bq) / 2
    prep = eu.prepare(books154, opens)
    summarize, account = eu.summarize, eu.ACCOUNT
    paths = {}

    def run(name, share):
        cap = {}

        def grab(idx, net, eq, eq_min, g, stats, eq_max=None):
            cap.update(idx=idx, net=net, eq=eq.copy(), eq_min=eq_min.copy(), g=g.copy(), stats=dict(stats),
                       eq_max=(eq if eq_max is None else eq_max).copy())
            return {}
        eu.summarize, eu.ACCOUNT = grab, account * share
        try:
            eu.simulate(books, opens, prep, trade=dict(v216.GRID, policy=POLICIES[name]()), win_start=5, **KW)
        finally:
            eu.summarize, eu.ACCOUNT = summarize, account
        return cap

    def combine(weights):
        parts = {}
        for name, w in weights.items():
            key = (name, round(w, 6))
            if key not in paths:
                paths[key] = run(name, w)
            parts[name] = (w, paths[key])
        any_ = next(iter(parts.values()))[1]
        eq = sum(w * p["eq"] for w, p in parts.values())
        eq_min = sum(w * p["eq_min"] for w, p in parts.values())
        eq_max = sum(w * p["eq_max"] for w, p in parts.values())
        g = sum(w * p["g"] for w, p in parts.values())
        stats = {k: sum(p["stats"][k] for _, p in parts.values()) for k in ("fills", "stops", "tps")}
        net = np.concatenate([[eq[0] - 1], eq[1:] / eq[:-1] - 1])
        r = summarize(any_["idx"], net, eq, eq_min, g, stats, eq_max)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        return r

    out = {"version": "v222", "variants": VARIANTS, "rows": {}}
    for key, wts in [("v218_D2", {"D2": 1.0})] + list(VARIANTS.items()):
        r = combine(wts)
        out["rows"][key] = r
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]], flush=True)
        if key == "v218_D2":
            assert abs(r["monthly_dev4"] - 5.261) < 0.002
    sel = v204.robust_select({k: out["rows"][k] for k in VARIANTS})
    s = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s["monthly_5y"], "monthly_last_year": s["monthly_last_year"],
                                   "losing_years": s["losing_years"], "gate_dd": s["gate_dd"], "gate_pass": s["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s["yearly"]]}
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v222_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
